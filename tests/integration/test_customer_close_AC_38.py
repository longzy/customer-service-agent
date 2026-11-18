"""F-11：客户关闭会话（AC-38 客户侧）。

- 客户在 `AI_ACTIVE`/`QUEUED`/`CLAIMED`/`HUMAN_ACTIVE` 均可关闭；会话与 open 交接单
  在同一事务内终态化，并写一条“会话已结束”系统消息。
- 关闭后再发消息 409 `CONVERSATION_CLOSED` 且不落库；读历史仍 200 并返回 `CLOSED`。
- 关闭幂等：重复关闭 200、系统消息只写一条、`closed_at` 不变。
- 客户隔离与并发：关闭只影响自己的会话；客户关闭与坐席领取并发后状态一致。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.platform.models import ServiceConversation, ServiceHandoff, ServiceMessage
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
CLOSE = "/customer/session/close"
CUSTOMER_MESSAGES = "/customer/messages"
CLOSED_NOTICE = "会话已结束"


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client() -> TestClient:
    return TestClient(create_app())


def conversation_of(conversation_id: str) -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def handoff_of(handoff_id: str) -> ServiceHandoff:
    return next(row for row in rows_of(ServiceHandoff) if row.id == handoff_id)


def closed_notices(conversation_id: str) -> list[ServiceMessage]:
    return [
        row
        for row in rows_of(ServiceMessage)
        if row.conversation_id == conversation_id and row.content == CLOSED_NOTICE
    ]


def test_客户在排队中关闭会话并同事务终态交接单_AC_38() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as api:
        login_customer(api, "customer_a")
        response = api.post(CLOSE)

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
    assert conversation.updated_at >= BASE

    handoff = handoff_of("ho-1")
    assert handoff.status == "CLOSED"
    assert handoff.pending_step == CLOSED_NOTICE
    assert handoff.version == 1

    with api_client() as workspace_api:
        login_employee(workspace_api, "agent_1")
        queue = workspace_api.get("/workspace/queue")

    assert queue.status_code == 200, queue.text
    assert queue.json()["items"] == []


def test_客户在人工中关闭会话后历史仍可读_AC_38() -> None:
    seed_queued_handoff(
        "ho-2",
        conversation_id="conv-2",
        customer_id="cust-customer_a",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
        last_message="我还有一个问题",
    )

    with api_client() as api:
        login_customer(api, "customer_a")
        closed = api.post(CLOSE)
        history = api.get(CUSTOMER_MESSAGES, params={"after_id": 0})

    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "CLOSED"
    assert history.status_code == 200, history.text
    page = history.json()
    assert page["status"] == "CLOSED"
    contents = [item["content"] for item in page["messages"]]
    assert "我还有一个问题" in contents
    assert CLOSED_NOTICE in contents


def test_客户在AI会话中关闭不触碰交接单_AC_38() -> None:
    seed_conversation("conv-3", customer_id="cust-customer_a", status="AI_ACTIVE")

    with api_client() as api:
        login_customer(api, "customer_a")
        response = api.post(CLOSE)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CLOSED"
    assert len(rows_of(ServiceHandoff)) == 0
    assert conversation_of("conv-3").status == "CLOSED"
    assert len(closed_notices("conv-3")) == 1


def test_关闭后再发消息409且不落库_AC_38() -> None:
    seed_conversation("conv-4", customer_id="cust-customer_a", status="AI_ACTIVE")

    with api_client() as api:
        login_customer(api, "customer_a")
        assert api.post(CLOSE).status_code == 200
        before = len(rows_of(ServiceMessage))
        sent = api.post(
            CUSTOMER_MESSAGES,
            json={"content": "还在吗"},
            headers={"Idempotency-Key": "after-close-1"},
        )

    assert sent.status_code == 409
    assert sent.json()["code"] == "CONVERSATION_CLOSED"
    assert len(rows_of(ServiceMessage)) == before
    assert conversation_of("conv-4").status == "CLOSED"


def test_重复关闭幂等且系统消息只写一条_AC_38() -> None:
    seed_conversation("conv-5", customer_id="cust-customer_a", status="AI_ACTIVE")

    with api_client() as api:
        login_customer(api, "customer_a")
        first = api.post(CLOSE)
        closed_at = conversation_of("conv-5").closed_at
        second = api.post(CLOSE)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "CLOSED"
    assert second.json()["messages"] == []
    assert len(closed_notices("conv-5")) == 1
    assert conversation_of("conv-5").closed_at == closed_at
    assert conversation_of("conv-5").status == "CLOSED"


def test_关闭会话未登录401_AC_38() -> None:
    seed_conversation("conv-6", customer_id="cust-customer_a", status="AI_ACTIVE")

    with api_client() as api:
        response = api.post(CLOSE)

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_INVALID"
    assert conversation_of("conv-6").status == "AI_ACTIVE"


def test_客户关闭只影响自己的会话_AC_38() -> None:
    seed_queued_handoff(
        "ho-a",
        conversation_id="conv-a",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    seed_queued_handoff(
        "ho-b",
        conversation_id="conv-b",
        customer_id="cust-customer_b",
        created_at=BASE,
    )

    with api_client() as api:
        login_customer(api, "customer_a")
        response = api.post(CLOSE)

    assert response.status_code == 200, response.text
    assert conversation_of("conv-a").status == "CLOSED"
    assert handoff_of("ho-a").status == "CLOSED"
    assert conversation_of("conv-b").status == "QUEUED"
    assert handoff_of("ho-b").status == "QUEUED"


def test_客户关闭与坐席领取并发后状态一致_AC_38() -> None:
    seed_queued_handoff(
        "ho-race",
        conversation_id="conv-race",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    barrier = threading.Barrier(2)

    def close_attempt() -> tuple[str, int, dict[str, Any]]:
        with api_client() as api:
            login_customer(api, "customer_a")
            barrier.wait(timeout=10)
            response = api.post(CLOSE)
            return "customer", response.status_code, response.json()

    def claim_attempt() -> tuple[str, int, dict[str, Any]]:
        with api_client() as api:
            login_employee(api, "agent_1")
            barrier.wait(timeout=10)
            response = api.post("/workspace/queue/ho-race/claim")
            return "agent", response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(close_attempt), pool.submit(claim_attempt)]
        results = [future.result(timeout=30) for future in futures]

    statuses = {actor: status for actor, status, _ in results}
    assert statuses["customer"] == 200, results
    assert statuses["agent"] in (200, 409), results

    assert conversation_of("conv-race").status == "CLOSED"
    assert handoff_of("ho-race").status == "CLOSED"

    with api_client() as workspace_api:
        login_employee(workspace_api, "agent_1")
        queue = workspace_api.get("/workspace/queue")

    assert queue.json()["items"] == []


def test_坐席轮询看到客户已关闭_AC_38() -> None:
    seed_queued_handoff(
        "ho-9",
        conversation_id="conv-9",
        customer_id="cust-customer_a",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
    )

    with api_client() as customer_api:
        login_customer(customer_api, "customer_a")
        assert customer_api.post(CLOSE).status_code == 200

    with api_client() as workspace_api:
        login_employee(workspace_api, "agent_1")
        page = workspace_api.get("/workspace/conversations/conv-9/messages")
        detail = workspace_api.get("/workspace/conversations/conv-9")

    assert page.status_code == 200, page.text
    assert page.json()["status"] == "CLOSED"
    assert CLOSED_NOTICE in [item["content"] for item in page.json()["messages"]]

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "CLOSED"
    assert body["handoff"]["status"] == "CLOSED"
    assert body["handoff"]["pending_step"] == CLOSED_NOTICE
