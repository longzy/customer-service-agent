"""F-08：领取后接管与完整上下文（AC-36）。

- 领取后客户收到“正在接入人工”，接管后收到“人工已接入”（plan 3.4）。
- 接管把会话 `CLAIMED → HUMAN_ACTIVE`、交接单 `CLAIMED → ACTIVE`，同事务写系统消息。
- 领取者读取客户账号、消息、AI 轨迹、交接单与待办；未领取/第二坐席/跨租户 404。
- 已关闭会话接管 409 `CONVERSATION_CLOSED`；未登录 401、非坐席 403。
"""

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
    seed_customer,
    seed_queued_handoff,
    set_employee_role,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

BASE = datetime(2026, 11, 17, 10, 0, 0, tzinfo=UTC)
CLAIM = "/workspace/queue/{handoff_id}/claim"
TAKEOVER = "/workspace/conversations/{conversation_id}/takeover"
DETAIL = "/workspace/conversations/{conversation_id}"

CONTEXT: dict[str, object] = {
    "order_count": 0,
    "trigger": "keyword",
    "customer_username": "customer_a",
    "customer_display_name": "客户甲",
    "messages": [
        {
            "id": 1,
            "author_type": "customer",
            "content": "转人工",
            "created_at": "2026-11-17T10:00:00Z",
        }
    ],
    "ai_trace": [
        {
            "event_type": "intent",
            "name": "handoff_keyword",
            "status": "matched",
            "confidence": None,
            "created_at": "2026-11-17T10:00:00Z",
        }
    ],
}


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client() -> TestClient:
    return TestClient(create_app())


def freeze_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(
        "backend.conversations.workspace_conversations.utc_now",
        lambda: moment,
    )


def claim(api: TestClient, handoff_id: str) -> Any:
    return api.post(CLAIM.format(handoff_id=handoff_id))


def take_over(api: TestClient, conversation_id: str, *, trace_id: str | None = None) -> Any:
    headers = {"X-Request-ID": trace_id} if trace_id is not None else {}
    return api.post(TAKEOVER.format(conversation_id=conversation_id), headers=headers)


def detail(api: TestClient, conversation_id: str) -> Any:
    return api.get(DETAIL.format(conversation_id=conversation_id))


def handoff_of(handoff_id: str) -> ServiceHandoff:
    return next(row for row in rows_of(ServiceHandoff) if row.id == handoff_id)


def conversation_of(conversation_id: str) -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def system_messages(conversation_id: str) -> list[str]:
    return [
        row.content
        for row in rows_of(ServiceMessage)
        if row.conversation_id == conversation_id and row.author_type == "system"
    ]


def test_领取后客户看到正在接入人工_AC_36(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clock(monkeypatch, BASE)
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
        last_message="转人工",
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        assert claim(api, "ho-1").status_code == 200

    with api_client() as customer_api:
        login_customer(customer_api, "customer_a")
        page = customer_api.get("/customer/messages", params={"after_id": 0})

    assert page.status_code == 200, page.text
    body = page.json()
    assert body["status"] == "CLAIMED"
    assert system_messages("conv-1") == ["排队中，请稍候", "正在接入人工"]
    assert [item["content"] for item in body["messages"] if item["author_type"] == "system"] == [
        "排队中，请稍候",
        "正在接入人工",
    ]


def test_接管后客户看到人工已接入_AC_36(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clock(monkeypatch, BASE)
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
        last_message="转人工",
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        assert claim(api, "ho-1").status_code == 200
        response = take_over(api, "conv-1", trace_id="trace-takeover")

    assert response.status_code == 200, response.text
    assert response.json() == {"conversation_id": "conv-1", "status": "HUMAN_ACTIVE"}

    handoff = handoff_of("ho-1")
    assert handoff.status == "ACTIVE"
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.version == 2
    conversation = conversation_of("conv-1")
    assert conversation.status == "HUMAN_ACTIVE"
    assert conversation.assigned_employee_id == "emp-agent_1"

    notice = next(
        row
        for row in rows_of(ServiceMessage)
        if row.conversation_id == "conv-1"
        and row.author_type == "system"
        and row.content == "人工已接入"
    )
    assert notice.trace_id == "trace-takeover"

    with api_client() as customer_api:
        login_customer(customer_api, "customer_a")
        page = customer_api.get("/customer/messages", params={"after_id": 0})

    assert page.status_code == 200, page.text
    body = page.json()
    assert body["status"] == "HUMAN_ACTIVE"
    assert [item["content"] for item in body["messages"] if item["author_type"] == "system"][
        -1
    ] == "人工已接入"


def test_接管后可读客户消息与AI轨迹交接单_AC_36(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clock(monkeypatch, BASE)
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
        summary="客户甲要求转人工",
        context=CONTEXT,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        assert claim(api, "ho-1").status_code == 200
        response = detail(api, "conv-1")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "conv-1"
    assert body["status"] == "CLAIMED"
    assert body["customer"] == {"username": "customer_a", "display_name": "客户甲"}

    handoff = body["handoff"]
    assert handoff["id"] == "ho-1"
    assert handoff["status"] == "CLAIMED"
    assert handoff["reason"] == "CUSTOMER_REQUEST"
    assert handoff["summary"] == "客户甲要求转人工"
    assert handoff["pending_step"] == "等待坐席接入"
    assert handoff["order_count"] == 0
    assert handoff["messages"] == [
        {
            "id": 1,
            "author_type": "customer",
            "content": "转人工",
            "created_at": "2026-11-17T10:00:00Z",
        }
    ]
    assert handoff["ai_trace"] == [
        {
            "event_type": "intent",
            "name": "handoff_keyword",
            "status": "matched",
            "confidence": None,
            "created_at": "2026-11-17T10:00:00Z",
        }
    ]


def test_第二坐席查看与接管已领取会话404_AC_36() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as first:
        login_employee(first, "agent_1")
        assert claim(first, "ho-1").status_code == 200

    with api_client() as second:
        login_employee(second, "agent_2")
        read = detail(second, "conv-1")
        took_over = take_over(second, "conv-1")

    assert read.status_code == 404
    assert read.json()["code"] == "NOT_FOUND"
    assert took_over.status_code == 404
    assert took_over.json()["code"] == "NOT_FOUND"
    assert handoff_of("ho-1").status == "CLAIMED"
    assert handoff_of("ho-1").claimed_by == "emp-agent_1"
    assert conversation_of("conv-1").status == "CLAIMED"


def test_未领取会话不能接管404_AC_36() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = take_over(api, "conv-1")
        read = detail(api, "conv-1")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert read.status_code == 404
    assert handoff_of("ho-1").status == "QUEUED"
    assert conversation_of("conv-1").status == "QUEUED"


def test_已关闭会话接管409_AC_36() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        status="CLOSED",
        conversation_status="CLOSED",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = take_over(api, "conv-1")

    assert response.status_code == 409
    assert response.json()["code"] == "CONVERSATION_CLOSED"
    assert handoff_of("ho-1").status == "CLOSED"
    assert conversation_of("conv-1").status == "CLOSED"


def test_重复接管已人工会话404_AC_36() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        assert claim(api, "ho-1").status_code == 200
        assert take_over(api, "conv-1").status_code == 200
        repeated = take_over(api, "conv-1")

    assert repeated.status_code == 404
    assert repeated.json()["code"] == "NOT_FOUND"
    assert handoff_of("ho-1").status == "ACTIVE"
    assert handoff_of("ho-1").version == 2
    assert system_messages("conv-1").count("人工已接入") == 1


def test_未登录401且非坐席403_AC_36() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        assigned_employee_id="emp-agent_1",
        conversation_status="CLAIMED",
        status="CLAIMED",
        created_at=BASE,
    )

    with api_client() as api:
        anonymous = take_over(api, "conv-1")
        login_employee(api, "agent_1")
        set_employee_role("agent_1", "supervisor")
        forbidden = take_over(api, "conv-1")

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "SESSION_INVALID"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert conversation_of("conv-1").status == "CLAIMED"


def test_跨租户会话接管404_AC_36() -> None:
    seed_customer(
        "cust-tenant-b",
        "customer_b",
        tenant_id="tenant-b",
        display_name="租户乙客户",
    )
    seed_queued_handoff(
        "ho-other-tenant",
        conversation_id="conv-other-tenant",
        customer_id="cust-tenant-b",
        status="CLAIMED",
        conversation_status="CLAIMED",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
        tenant_id="tenant-b",
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        read = detail(api, "conv-other-tenant")
        took_over = take_over(api, "conv-other-tenant")

    assert read.status_code == 404
    assert took_over.status_code == 404
    assert handoff_of("ho-other-tenant").status == "CLAIMED"
    assert conversation_of("conv-other-tenant").status == "CLAIMED"
