"""F-10：坐席回复持久化与客户 3s 轮询可见（AC-37）。

- 接管后坐席回复：落 `service_messages`（`agent`/`author_id` 为员工），客户按 `after_id`
  游标轮询可见，回复不改变会话/交接单状态。
- 人工中客户消息只落库，不调用模型、不写 AI 事件、不新建交接单；工作台轮询可见。
- 归属/状态矩阵：第二坐席回复与轮询 404，未接管（CLAIMED）回复 404，已关闭回复 409。
- 回复幂等：同一 `Idempotency-Key` 重放返回同一条消息，库里只有一条。
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.agent_runtime.model import ChatReply
from backend.api.main import create_app
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceHandoff,
    ServiceMessage,
)
from tests.integration.customer_support import login_customer
from tests.integration.db_utils import db_available
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
    rows_of,
    seed_queued_handoff,
    set_employee_role,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

BASE = datetime(2026, 11, 18, 10, 0, 0, tzinfo=UTC)
REPLY = "/workspace/conversations/{conversation_id}/messages"
CUSTOMER_MESSAGES = "/customer/messages"
AGENT_REPLY = "您好，我是坐席 1"


class UnexpectedModel:
    """人工中不应调用模型；被调用即失败。"""

    async def respond(self, _message: str) -> ChatReply:
        raise AssertionError("人工中不应调用模型")


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client(model: Any = None) -> TestClient:
    app = create_app()
    app.state.model_client = model or UnexpectedModel()
    return TestClient(app)


def seed_human_active(
    *,
    status: str = "ACTIVE",
    conversation_status: str = "HUMAN_ACTIVE",
    assigned_employee_id: str | None = "emp-agent_1",
    handoff_id: str = "ho-1",
    conversation_id: str = "conv-1",
) -> None:
    """播种一张已接管会话；客户与员工种子由 `prepare_workspace_db` 提供。"""

    seed_queued_handoff(
        handoff_id,
        conversation_id=conversation_id,
        customer_id="cust-customer_a",
        status=status,
        conversation_status=conversation_status,
        assigned_employee_id=assigned_employee_id,
        created_at=BASE - timedelta(hours=1),
    )


def reply(api: TestClient, content: str = AGENT_REPLY, *, key: str = "reply-key-1") -> Any:
    return api.post(
        REPLY.format(conversation_id="conv-1"),
        json={"content": content},
        headers={"Idempotency-Key": key, "X-Request-ID": "trace-reply-1"},
    )


def read_workspace_messages(api: TestClient, after_id: int = 0) -> Any:
    return api.get(
        REPLY.format(conversation_id="conv-1"),
        params={"after_id": after_id},
    )


def messages_of(conversation_id: str = "conv-1") -> list[ServiceMessage]:
    return [row for row in rows_of(ServiceMessage) if row.conversation_id == conversation_id]


def agent_messages(conversation_id: str = "conv-1") -> list[ServiceMessage]:
    return [row for row in messages_of(conversation_id) if row.author_type == "agent"]


def conversation_of(conversation_id: str = "conv-1") -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def test_坐席回复持久化且客户轮询可见_AC_37() -> None:
    seed_human_active()

    with api_client() as api:
        login_employee(api, "agent_1")
        response = reply(api)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conversation_id"] == "conv-1"
    assert body["status"] == "HUMAN_ACTIVE"
    assert [item["author_type"] for item in body["messages"]] == ["agent"]
    assert body["messages"][0]["content"] == AGENT_REPLY
    message_id = body["messages"][0]["id"]
    assert body["after_id"] == message_id

    stored = agent_messages()
    assert len(stored) == 1
    assert stored[0].author_id == "emp-agent_1"
    assert stored[0].trace_id == "trace-reply-1"
    assert conversation_of().status == "HUMAN_ACTIVE"
    assert conversation_of().updated_at > BASE - timedelta(hours=1)

    with api_client() as customer_api:
        login_customer(customer_api, "customer_a")
        full = customer_api.get(CUSTOMER_MESSAGES, params={"after_id": 0})
        incremental = customer_api.get(CUSTOMER_MESSAGES, params={"after_id": message_id - 1})

    assert full.status_code == 200, full.text
    agent_contents = [
        item["content"] for item in full.json()["messages"] if item["author_type"] == "agent"
    ]
    assert agent_contents == [AGENT_REPLY]
    assert incremental.status_code == 200, incremental.text
    assert [item["content"] for item in incremental.json()["messages"]] == [AGENT_REPLY]
    assert incremental.json()["status"] == "HUMAN_ACTIVE"


def test_人工中客户消息不触发AI且工作台可见_AC_37() -> None:
    seed_human_active()
    events_before = len(rows_of(ServiceAiEvent))
    handoffs_before = len(rows_of(ServiceHandoff))

    with api_client() as customer_api:
        login_customer(customer_api, "customer_a")
        sent = customer_api.post(
            CUSTOMER_MESSAGES,
            json={"content": "我还是不太明白"},
            headers={"Idempotency-Key": "customer-human-key-1"},
        )

    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "HUMAN_ACTIVE"
    assert [item["author_type"] for item in body["messages"]] == ["customer"]
    assert body["messages"][0]["content"] == "我还是不太明白"

    stored = messages_of()
    assert [row.author_type for row in stored].count("ai") == 0
    assert [row.content for row in stored if row.author_type == "customer"] == ["我还是不太明白"]
    assert len(rows_of(ServiceAiEvent)) == events_before
    assert len(rows_of(ServiceHandoff)) == handoffs_before
    assert conversation_of().status == "HUMAN_ACTIVE"

    with api_client() as api:
        login_employee(api, "agent_1")
        page = read_workspace_messages(api)

    assert page.status_code == 200, page.text
    customer_contents = [
        item["content"] for item in page.json()["messages"] if item["author_type"] == "customer"
    ]
    assert customer_contents == ["我还是不太明白"]


def test_第二坐席回复与轮询404_AC_37() -> None:
    seed_human_active()

    with api_client() as api:
        login_employee(api, "agent_2")
        posted = reply(api, key="agent-2-key")
        read = read_workspace_messages(api)

    assert posted.status_code == 404
    assert posted.json()["code"] == "NOT_FOUND"
    assert read.status_code == 404
    assert read.json()["code"] == "NOT_FOUND"
    assert agent_messages() == []


def test_未接管回复404且轮询仍可读_AC_37() -> None:
    seed_human_active(status="CLAIMED", conversation_status="CLAIMED")

    with api_client() as api:
        login_employee(api, "agent_1")
        posted = reply(api)
        read = read_workspace_messages(api)

    assert posted.status_code == 404
    assert posted.json()["code"] == "NOT_FOUND"
    assert agent_messages() == []
    assert conversation_of().status == "CLAIMED"
    assert read.status_code == 200, read.text
    assert read.json()["status"] == "CLAIMED"


def test_已关闭会话回复409_AC_37() -> None:
    seed_human_active(
        status="CLOSED",
        conversation_status="CLOSED",
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        posted = reply(api)
        read = read_workspace_messages(api)

    assert posted.status_code == 409
    assert posted.json()["code"] == "CONVERSATION_CLOSED"
    assert agent_messages() == []
    assert read.status_code == 200, read.text
    assert read.json()["status"] == "CLOSED"


def test_回复未登录401非坐席403_AC_37() -> None:
    seed_human_active()

    with api_client() as api:
        anonymous = reply(api)
        login_employee(api, "agent_1")
        set_employee_role("agent_1", "supervisor")
        forbidden = reply(api)

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "SESSION_INVALID"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert agent_messages() == []


def test_重复回复同一幂等键只有一条_AC_37() -> None:
    seed_human_active()

    with api_client() as api:
        login_employee(api, "agent_1")
        first = reply(api)
        second = reply(api)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["messages"][0]["id"] == second.json()["messages"][0]["id"]
    stored = agent_messages()
    assert len(stored) == 1
    assert stored[0].content == AGENT_REPLY


def test_回复空正文或超长422_AC_37() -> None:
    seed_human_active()

    with api_client() as api:
        login_employee(api, "agent_1")
        blank = reply(api, "   ", key="blank-key")
        too_long = reply(api, "好" * 501, key="long-key")
        missing_header = api.post(REPLY.format(conversation_id="conv-1"), json={"content": "在吗"})

    assert blank.status_code == 422
    assert too_long.status_code == 422
    assert missing_header.status_code == 422
    assert agent_messages() == []


def test_未接管客户消息仍不触发AI_AC_37() -> None:
    """队列/已领取阶段同样不调用模型；F-02 已实现，这里锁定 AC-37 的完整状态面。"""

    seed_human_active(status="QUEUED", conversation_status="QUEUED", assigned_employee_id=None)
    events_before = len(rows_of(ServiceAiEvent))

    with api_client() as customer_api:
        login_customer(customer_api, "customer_a")
        sent = customer_api.post(
            CUSTOMER_MESSAGES,
            json={"content": "转人工后我又补充了一句"},
            headers={"Idempotency-Key": "customer-queued-key-1"},
        )

    assert sent.status_code == 200, sent.text
    assert [item["author_type"] for item in sent.json()["messages"]] == ["customer"]
    assert len(rows_of(ServiceAiEvent)) == events_before
