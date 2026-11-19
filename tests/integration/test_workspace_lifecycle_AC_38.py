"""F-12：坐席关闭会话与转回 AI（AC-38 坐席侧）。

- 坐席在 `CLAIMED`/`HUMAN_ACTIVE` 关闭：会话与 open 交接单同事务终态化，写“会话已结束”。
- 坐席在 `HUMAN_ACTIVE` 转回 AI：会话 `AI_ACTIVE`、assignment 清空、旧交接单 `CLOSED`，
  系统消息“已转回 AI 客服”；客户在同一会话继续对话且历史保留。
- 转回后客户再次要求转人工：生成新交接单，旧单已关闭；同一会话始终只有一张 open 单。
- 权限/状态：他人与跨租户 404；已关闭关闭 409；非人工中转回 404；转回后归属清除（404）。
- 幂等：同键重放返回首次系统消息；关闭新键在已关闭会话 409；转回新键在非人工中 404。
- 旧关闭键作用域是会话：客户关闭后登录新建会话，旧键不会跨会话重放（F-11 评审承接）。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.agent_runtime.model import FakeModelClient
from backend.api.main import create_app
from backend.platform.models import (
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
    seed_conversation,
    seed_queued_handoff,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

BASE = datetime(2026, 11, 18, 10, 0, 0, tzinfo=UTC)
AGENT_CLOSE = "/workspace/conversations/{conversation_id}/close"
RETURN_TO_AI = "/workspace/conversations/{conversation_id}/return-to-ai"
AGENT_REPLY = "/workspace/conversations/{conversation_id}/messages"
CUSTOMER_MESSAGES = "/customer/messages"
CUSTOMER_CLOSE = "/customer/session/close"
CLOSED_NOTICE = "会话已结束"
RETURN_NOTICE = "已转回 AI 客服"
PENDING_STEP = "等待坐席接入"


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client() -> TestClient:
    return TestClient(create_app())


def model_client() -> TestClient:
    app = create_app()
    app.state.model_client = FakeModelClient(
        {
            "继续聊聊": {
                "intent": "UNKNOWN",
                "confidence": 0.95,
                "reply": "当然可以，请说说您的问题。",
            }
        }
    )
    return TestClient(app)


def agent_close(api: TestClient, conversation_id: str, *, key: str = "agent-close-1") -> Any:
    return api.post(
        AGENT_CLOSE.format(conversation_id=conversation_id),
        headers={"Idempotency-Key": key},
    )


def return_to_ai(api: TestClient, conversation_id: str, *, key: str = "return-ai-1") -> Any:
    return api.post(
        RETURN_TO_AI.format(conversation_id=conversation_id),
        headers={"Idempotency-Key": key},
    )


def conversation_of(conversation_id: str) -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def handoffs_of(conversation_id: str) -> list[ServiceHandoff]:
    return sorted(
        (row for row in rows_of(ServiceHandoff) if row.conversation_id == conversation_id),
        key=lambda row: (row.created_at, row.id),
    )


def messages_of(conversation_id: str) -> list[ServiceMessage]:
    return [row for row in rows_of(ServiceMessage) if row.conversation_id == conversation_id]


def seed_human_active(conversation_id: str = "conv-1", handoff_id: str = "ho-1") -> None:
    seed_queued_handoff(
        handoff_id,
        conversation_id=conversation_id,
        customer_id="cust-customer_a",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
        earlier_messages=("我要转人工",),
        last_message="帮我看看这个",
    )


def test_坐席在人工中关闭会话_AC_38() -> None:
    seed_human_active()

    with api_client() as customer_api:
        login_customer(customer_api)
        assert customer_api.get(CUSTOMER_MESSAGES).json()["status"] == "HUMAN_ACTIVE"

        with api_client() as agent_api:
            login_employee(agent_api, "agent_1")
            response = agent_close(agent_api, "conv-1")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["conversation_id"] == "conv-1"
        assert body["status"] == "CLOSED"
        assert [item["content"] for item in body["messages"]] == [CLOSED_NOTICE]
        assert body["messages"][0]["author_type"] == "system"
        assert body["after_id"] == body["messages"][0]["id"]

        conversation = conversation_of("conv-1")
        assert conversation.status == "CLOSED"
        assert conversation.closed_at is not None

        handoff = handoffs_of("conv-1")[0]
        assert handoff.status == "CLOSED"
        assert handoff.version == 1
        # 待办是转人工时点的快照；关闭不重写（F-11 D-4 / 本卡 D-6）。
        assert handoff.pending_step == PENDING_STEP

        notices = [row for row in messages_of("conv-1") if row.content == CLOSED_NOTICE]
        assert len(notices) == 1
        assert notices[0].idempotency_key == "agent-close-1"

        history = customer_api.get(CUSTOMER_MESSAGES, params={"after_id": 0})
        assert history.status_code == 200, history.text
        assert history.json()["status"] == "CLOSED"
        assert "我要转人工" in [item["content"] for item in history.json()["messages"]]

        after_close = customer_api.post(
            CUSTOMER_MESSAGES,
            json={"content": "还在吗"},
            headers={"Idempotency-Key": "after-agent-close-1"},
        )
        assert after_close.status_code == 409
        assert after_close.json()["code"] == "CONVERSATION_CLOSED"

    with api_client() as queue_api:
        login_employee(queue_api, "agent_1")
        assert queue_api.get("/workspace/queue").json()["items"] == []


def test_坐席在已领取未接管时关闭会话_AC_38() -> None:
    seed_queued_handoff(
        "ho-claimed",
        conversation_id="conv-claimed",
        customer_id="cust-customer_a",
        status="CLAIMED",
        conversation_status="CLAIMED",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = agent_close(api, "conv-claimed", key="claimed-close-1")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CLOSED"
    assert conversation_of("conv-claimed").status == "CLOSED"
    handoff = handoffs_of("conv-claimed")[0]
    assert handoff.status == "CLOSED"
    assert handoff.pending_step == PENDING_STEP


def test_转回AI后客户继续对话且历史保留_AC_38() -> None:
    seed_human_active("conv-return", "ho-return")

    with model_client() as customer_api:
        login_customer(customer_api)

        with api_client() as agent_api:
            login_employee(agent_api, "agent_1")
            response = return_to_ai(agent_api, "conv-return")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "AI_ACTIVE"
        assert [item["content"] for item in body["messages"]] == [RETURN_NOTICE]

        conversation = conversation_of("conv-return")
        assert conversation.status == "AI_ACTIVE"
        assert conversation.assigned_employee_id is None
        assert conversation.closed_at is None

        handoff = handoffs_of("conv-return")[0]
        assert handoff.status == "CLOSED"
        assert handoff.version == 1
        assert handoff.pending_step == PENDING_STEP

        page = customer_api.get(CUSTOMER_MESSAGES, params={"after_id": 0})
        assert page.status_code == 200, page.text
        assert page.json()["status"] == "AI_ACTIVE"
        contents = [item["content"] for item in page.json()["messages"]]
        assert "我要转人工" in contents
        assert RETURN_NOTICE in contents

        sent = customer_api.post(
            CUSTOMER_MESSAGES,
            json={"content": "继续聊聊"},
            headers={"Idempotency-Key": "after-return-1"},
        )
        assert sent.status_code == 200, sent.text
        sent_body = sent.json()
        assert sent_body["status"] == "AI_ACTIVE"
        assert [item["author_type"] for item in sent_body["messages"]] == ["customer", "ai"]
        assert sent_body["messages"][1]["content"] == "当然可以，请说说您的问题。"

        history = customer_api.get(CUSTOMER_MESSAGES, params={"after_id": 0})
        assert "我要转人工" in [item["content"] for item in history.json()["messages"]]


def test_转回AI后再次转人工生成新交接单_AC_38() -> None:
    seed_human_active("conv-again", "ho-again")

    with api_client() as agent_api:
        login_employee(agent_api, "agent_1")
        assert return_to_ai(agent_api, "conv-again", key="return-again-1").status_code == 200

    with api_client() as customer_api:
        login_customer(customer_api)
        first = customer_api.post(
            CUSTOMER_MESSAGES,
            json={"content": "转人工"},
            headers={"Idempotency-Key": "handoff-again-1"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "QUEUED"

        # 排队中再发“转人工”不新建第二张 open 单（create_handoff 复用 open 单）。
        second = customer_api.post(
            CUSTOMER_MESSAGES,
            json={"content": "转人工"},
            headers={"Idempotency-Key": "handoff-again-2"},
        )
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "QUEUED"

    handoffs = handoffs_of("conv-again")
    assert len(handoffs) == 2
    old, new = handoffs
    assert old.id == "ho-again"
    assert old.status == "CLOSED"
    assert old.version == 1
    assert new.status == "QUEUED"
    assert new.version == 0
    open_handoffs = [row for row in handoffs if row.status in {"QUEUED", "CLAIMED", "ACTIVE"}]
    assert len(open_handoffs) == 1

    with api_client() as queue_api:
        login_employee(queue_api, "agent_1")
        items = queue_api.get("/workspace/queue").json()["items"]

    assert [item["handoff_id"] for item in items] == [new.id]
    assert conversation_of("conv-again").status == "QUEUED"


def test_转回AI后坐席再操作404_AC_38() -> None:
    seed_human_active("conv-gone", "ho-gone")

    with api_client() as agent_api:
        login_employee(agent_api, "agent_1")
        assert return_to_ai(agent_api, "conv-gone", key="return-gone-1").status_code == 200

        closed = agent_close(agent_api, "conv-gone", key="close-gone-1")
        returned = return_to_ai(agent_api, "conv-gone", key="return-gone-2")
        replied = agent_api.post(
            AGENT_REPLY.format(conversation_id="conv-gone"),
            json={"content": "还在吗"},
            headers={"Idempotency-Key": "reply-gone-1"},
        )
        messages = agent_api.get(AGENT_REPLY.format(conversation_id="conv-gone"))
        detail = agent_api.get("/workspace/conversations/conv-gone")

    assert closed.status_code == 404, closed.text
    assert returned.status_code == 404, returned.text
    assert replied.status_code == 404, replied.text
    assert messages.status_code == 404, messages.text
    assert detail.status_code == 404, detail.text
    assert conversation_of("conv-gone").status == "AI_ACTIVE"


def test_转回AI非人工中404_AC_38() -> None:
    seed_queued_handoff(
        "ho-claimed-return",
        conversation_id="conv-claimed-return",
        customer_id="cust-customer_a",
        status="CLAIMED",
        conversation_status="CLAIMED",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = return_to_ai(api, "conv-claimed-return", key="claimed-return-1")

    assert response.status_code == 404, response.text
    assert conversation_of("conv-claimed-return").status == "CLAIMED"
    assert handoffs_of("conv-claimed-return")[0].status == "CLAIMED"


def test_坐席关闭与转回他人会话404_AC_38() -> None:
    seed_human_active("conv-owned", "ho-owned")

    with api_client() as owner_api:
        login_employee(owner_api, "agent_1")
        assert agent_close(owner_api, "conv-owned", key="owner-close-1").status_code == 200

    with api_client() as second_api:
        login_employee(second_api, "agent_2")
        denied_close = agent_close(second_api, "conv-owned", key="second-close-1")
        denied_return = return_to_ai(second_api, "conv-owned", key="second-return-1")

    assert denied_close.status_code == 404, denied_close.text
    assert denied_return.status_code == 404, denied_return.text

    # 客户关闭后 assignment 保留，第二坐席仍不可见；原坐席也不可再写。
    assert conversation_of("conv-owned").status == "CLOSED"
    notices = [row for row in messages_of("conv-owned") if row.content == CLOSED_NOTICE]
    assert len(notices) == 1


def test_坐席跨租户关闭与转回404_AC_38() -> None:
    seed_conversation(
        "conv-other-tenant",
        customer_id="cust-customer_a",
        status="HUMAN_ACTIVE",
        assigned_employee_id="emp-agent_1",
        tenant_id="tenant-other",
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        closed = agent_close(api, "conv-other-tenant", key="other-close-1")
        returned = return_to_ai(api, "conv-other-tenant", key="other-return-1")

    assert closed.status_code == 404, closed.text
    assert returned.status_code == 404, returned.text
    assert conversation_of("conv-other-tenant").status == "HUMAN_ACTIVE"


def test_坐席关闭与转回未登录401_AC_38() -> None:
    seed_human_active("conv-unauth", "ho-unauth")

    with api_client() as api:
        closed = agent_close(api, "conv-unauth", key="unauth-close-1")
        returned = return_to_ai(api, "conv-unauth", key="unauth-return-1")

    assert closed.status_code == 401
    assert closed.json()["code"] == "SESSION_INVALID"
    assert returned.status_code == 401
    assert conversation_of("conv-unauth").status == "HUMAN_ACTIVE"


def test_坐席关闭缺幂等键422_AC_38() -> None:
    seed_human_active("conv-no-key", "ho-no-key")

    with api_client() as api:
        login_employee(api, "agent_1")
        response = api.post(AGENT_CLOSE.format(conversation_id="conv-no-key"))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert conversation_of("conv-no-key").status == "HUMAN_ACTIVE"
    assert handoffs_of("conv-no-key")[0].status == "ACTIVE"


def test_坐席转回缺幂等键422_AC_38() -> None:
    seed_human_active("conv-return-no-key", "ho-return-no-key")

    with api_client() as api:
        login_employee(api, "agent_1")
        response = api.post(RETURN_TO_AI.format(conversation_id="conv-return-no-key"))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert conversation_of("conv-return-no-key").status == "HUMAN_ACTIVE"
    assert handoffs_of("conv-return-no-key")[0].status == "ACTIVE"


def test_坐席关闭同键重放且新键409_AC_38() -> None:
    seed_human_active("conv-replay", "ho-replay")

    with api_client() as api:
        login_employee(api, "agent_1")
        first = agent_close(api, "conv-replay", key="close-replay-1")
        closed_at = conversation_of("conv-replay").closed_at
        replay = agent_close(api, "conv-replay", key="close-replay-1")
        fresh = agent_close(api, "conv-replay", key="close-replay-2")

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["messages"] == first.json()["messages"]
    assert replay.json()["status"] == "CLOSED"
    assert fresh.status_code == 409
    assert fresh.json()["code"] == "CONVERSATION_CLOSED"

    notices = [row for row in messages_of("conv-replay") if row.content == CLOSED_NOTICE]
    assert len(notices) == 1
    assert conversation_of("conv-replay").closed_at == closed_at


def test_转回同键重放且新键404_AC_38() -> None:
    seed_human_active("conv-return-replay", "ho-return-replay")

    with api_client() as api:
        login_employee(api, "agent_1")
        first = return_to_ai(api, "conv-return-replay", key="return-replay-1")
        replay = return_to_ai(api, "conv-return-replay", key="return-replay-1")
        fresh = return_to_ai(api, "conv-return-replay", key="return-replay-2")

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["messages"] == first.json()["messages"]
    assert replay.json()["status"] == "AI_ACTIVE"
    assert fresh.status_code == 404, fresh.text

    notices = [row for row in messages_of("conv-return-replay") if row.content == RETURN_NOTICE]
    assert len(notices) == 1
    assert handoffs_of("conv-return-replay")[0].status == "CLOSED"


def test_坐席关闭已关闭会话409_AC_38() -> None:
    seed_queued_handoff(
        "ho-already-closed",
        conversation_id="conv-already-closed",
        customer_id="cust-customer_a",
        status="CLOSED",
        conversation_status="CLOSED",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = agent_close(api, "conv-already-closed", key="closed-close-1")

    assert response.status_code == 409
    assert response.json()["code"] == "CONVERSATION_CLOSED"
    assert [row for row in messages_of("conv-already-closed") if row.content == CLOSED_NOTICE] == []
    handoff = handoffs_of("conv-already-closed")[0]
    assert handoff.status == "CLOSED"
    assert handoff.version == 0


def test_坐席关闭与转回并发后状态一致_AC_38() -> None:
    seed_human_active("conv-race", "ho-race")
    barrier = threading.Barrier(2)

    def close_attempt() -> tuple[str, int, dict[str, Any]]:
        with api_client() as api:
            login_employee(api, "agent_1")
            barrier.wait(timeout=10)
            response = agent_close(api, "conv-race", key="race-close-1")
            return "close", response.status_code, response.json()

    def return_attempt() -> tuple[str, int, dict[str, Any]]:
        with api_client() as api:
            login_employee(api, "agent_1")
            barrier.wait(timeout=10)
            response = return_to_ai(api, "conv-race", key="race-return-1")
            return "return", response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(close_attempt), pool.submit(return_attempt)]
        results = [future.result(timeout=30) for future in futures]

    statuses = {actor: status for actor, status, _ in results}
    assert sorted(statuses.values()) in ([200, 404], [200, 409]), results

    conversation = conversation_of("conv-race")
    assert conversation.status in {"CLOSED", "AI_ACTIVE"}
    handoff = handoffs_of("conv-race")[0]
    assert handoff.status == "CLOSED"
    assert handoff.version == 1

    notices = [
        row for row in messages_of("conv-race") if row.content in {CLOSED_NOTICE, RETURN_NOTICE}
    ]
    assert len(notices) == 1
    winner = next(row for row in notices)
    if conversation.status == "CLOSED":
        assert winner.content == CLOSED_NOTICE
        assert conversation.closed_at is not None
    else:
        assert winner.content == RETURN_NOTICE
        assert conversation.assigned_employee_id is None


def test_客户关闭旧键不跨会话重放_AC_38() -> None:
    seed_conversation("conv-old", customer_id="cust-customer_a", status="AI_ACTIVE")

    with api_client() as api:
        login_customer(api)
        first = api.post(CUSTOMER_CLOSE, headers={"Idempotency-Key": "shared-close-key"})
        assert first.status_code == 200, first.text
        assert first.json()["conversation_id"] == "conv-old"

        # 关闭后读状态按 plan 3.3.2 新建会话；旧键只属于旧会话。
        current = api.get("/customer/session")
        assert current.status_code == 200, current.text
        new_id = current.json()["conversation"]["id"]
        assert new_id != "conv-old"

        second = api.post(CUSTOMER_CLOSE, headers={"Idempotency-Key": "shared-close-key"})

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["conversation_id"] == new_id
    assert [item["content"] for item in body["messages"]] == [CLOSED_NOTICE]
    assert body["after_id"] != first.json()["after_id"]
    assert conversation_of(new_id).status == "CLOSED"
