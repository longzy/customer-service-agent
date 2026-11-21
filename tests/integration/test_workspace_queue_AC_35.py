"""F-06：工作台队列 FIFO、摘要与领取前最小暴露（AC-35）。

- 队列只含同租户 `QUEUED` 交接单，按 `created_at, id` 升序。
- 摘要字段：客户账号/显示名、等待秒数、原因、订单数、脱敏末条（≤100 字）。
- 领取前不返回完整消息或交接单上下文；读队列不产生副作用。
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.platform.models import ServiceConversation, ServiceHandoff
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
QUEUE_KEYS = {
    "handoff_id",
    "conversation_id",
    "customer_username",
    "customer_display_name",
    "waiting_seconds",
    "reason",
    "order_count",
    "last_message",
}


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client() -> TestClient:
    return TestClient(create_app())


def freeze_queue_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(
        "backend.conversations.workspace_conversations.utc_now",
        lambda: moment,
    )


def queue_items(api: TestClient) -> list[dict[str, Any]]:
    response = api.get("/workspace/queue")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_队列按FIFO返回且只含QUEUED交接单_AC_35(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_queued_handoff(
        "ho-late",
        conversation_id="conv-late",
        customer_id="cust-customer_b",
        created_at=BASE + timedelta(minutes=2),
    )
    seed_queued_handoff(
        "ho-early",
        conversation_id="conv-early",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    seed_queued_handoff(
        "ho-middle",
        conversation_id="conv-middle",
        customer_id="cust-extra-1",
        created_at=BASE + timedelta(minutes=1),
    )
    seed_queued_handoff(
        "ho-claimed",
        conversation_id="conv-claimed",
        customer_id="cust-extra-2",
        status="CLAIMED",
        conversation_status="CLAIMED",
        created_at=BASE - timedelta(minutes=2),
    )
    seed_queued_handoff(
        "ho-active",
        conversation_id="conv-active",
        customer_id="cust-extra-3",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        created_at=BASE - timedelta(minutes=1),
    )
    seed_queued_handoff(
        "ho-closed",
        conversation_id="conv-closed",
        customer_id="cust-extra-4",
        status="CLOSED",
        conversation_status="CLOSED",
        created_at=BASE - timedelta(minutes=3),
    )
    freeze_queue_clock(monkeypatch, BASE + timedelta(minutes=5))

    with api_client() as api:
        login_employee(api)
        items = queue_items(api)

    assert [item["handoff_id"] for item in items] == ["ho-early", "ho-middle", "ho-late"]
    assert [item["customer_username"] for item in items] == [
        "customer_a",
        "extra_1",
        "customer_b",
    ]
    assert [item["waiting_seconds"] for item in items] == [300, 240, 180]


def test_队列同创建时间按交接单ID稳定排序_AC_35(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_queued_handoff(
        "ho-b",
        conversation_id="conv-b",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    seed_queued_handoff(
        "ho-a",
        conversation_id="conv-a",
        customer_id="cust-customer_b",
        created_at=BASE,
    )
    freeze_queue_clock(monkeypatch, BASE)

    with api_client() as api:
        login_employee(api)
        items = queue_items(api)

    assert [item["handoff_id"] for item in items] == ["ho-a", "ho-b"]


def test_队列摘要含账号等待原因脱敏末条与订单数_AC_35(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = "您好，手机 138-1234-5678，邮箱 user@example.com。" + "长" * 120 + "泄露标记ABC"
    seed_queued_handoff(
        "ho-summary",
        conversation_id="conv-summary",
        customer_id="cust-customer_a",
        reason="LOW_CONFIDENCE",
        created_at=BASE,
        order_count=0,
        earlier_messages=("较早一条，手机 13700001111",),
        last_message=content,
    )
    freeze_queue_clock(monkeypatch, BASE + timedelta(seconds=42))

    with api_client() as api:
        login_employee(api)
        response = api.get("/workspace/queue")
        items = queue_items(api)

    assert response.status_code == 200
    assert len(items) == 1
    item = items[0]
    assert item["customer_username"] == "customer_a"
    assert item["customer_display_name"] == "客户甲"
    assert item["waiting_seconds"] == 42
    assert item["reason"] == "LOW_CONFIDENCE"
    assert item["order_count"] == 0
    assert item["conversation_id"] == "conv-summary"
    # 系统“排队中，请稍候”不占用末条；摘要取客户最后一条消息并脱敏截断。
    assert not item["last_message"].startswith("排队中")
    assert len(item["last_message"]) <= 100
    assert "138****5678" in item["last_message"]
    assert "u***@example.com" in item["last_message"]
    assert "138-1234-5678" not in item["last_message"]
    assert "user@example.com" not in item["last_message"]
    assert "较早一条" not in item["last_message"]
    assert "13700001111" not in item["last_message"]
    assert "泄露标记ABC" not in response.text


def test_队列不返回完整消息与交接单上下文_未领取详情404_AC_35(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tail = "完整消息尾部标记DEF"
    content = "开头摘要" + "填" * 150 + tail
    seed_queued_handoff(
        "ho-minimal",
        conversation_id="conv-minimal",
        customer_id="cust-customer_a",
        last_message=content,
        created_at=BASE,
    )
    freeze_queue_clock(monkeypatch, BASE)

    with api_client() as api:
        login_employee(api)
        response = api.get("/workspace/queue")
        detail = api.get("/workspace/conversations/conv-minimal")

    item = response.json()["items"][0]
    assert set(item) == QUEUE_KEYS
    assert "messages" not in item
    assert "context" not in item
    assert "summary" not in item
    assert tail not in response.text
    # 领取前会话详情仍走 F-05 的归属门禁，未领取一律 404。
    assert detail.status_code == 404
    assert detail.json()["code"] == "NOT_FOUND"


def test_队列只返回同租户交接单_AC_35(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_queued_handoff(
        "ho-tenant-a",
        conversation_id="conv-tenant-a",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    seed_customer("cust-tenant-b", "customer_c", tenant_id="tenant-b", display_name="客户丙")
    seed_queued_handoff(
        "ho-tenant-b",
        conversation_id="conv-tenant-b",
        customer_id="cust-tenant-b",
        tenant_id="tenant-b",
        created_at=BASE - timedelta(minutes=1),
    )
    # 脏数据兜底：交接单属 tenant-a、客户属 tenant-b，也必须被客户租户条件挡住。
    seed_queued_handoff(
        "ho-customer-mismatch",
        conversation_id="conv-customer-mismatch",
        customer_id="cust-tenant-b",
        created_at=BASE - timedelta(minutes=2),
    )
    freeze_queue_clock(monkeypatch, BASE)

    with api_client() as api:
        login_employee(api)
        items = queue_items(api)

    assert [item["handoff_id"] for item in items] == ["ho-tenant-a"]


def test_空队列返回空列表_AC_35() -> None:
    with api_client() as api:
        login_employee(api)
        response = api.get("/workspace/queue")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_队列订单数取交接单快照值_AC_35(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_queued_handoff(
        "ho-order-count",
        conversation_id="conv-order-count",
        customer_id="cust-customer_a",
        created_at=BASE,
        order_count=7,
    )
    freeze_queue_clock(monkeypatch, BASE)

    with api_client() as api:
        login_employee(api)
        items = queue_items(api)

    # F-28：队列订单数来自交接单快照，不再恒 0（003 AC-55）。
    assert items[0]["order_count"] == 7


def test_未登录401且角色降级后403_AC_35() -> None:
    with api_client() as api:
        unauthorized = api.get("/workspace/queue")
        login_employee(api, "agent_1")
        allowed = api.get("/workspace/queue")
        set_employee_role("agent_1", "supervisor")
        forbidden = api.get("/workspace/queue")

    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "SESSION_INVALID"
    assert allowed.status_code == 200
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"


def test_读取队列不自动分配也不改动交接单_AC_35(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_queued_handoff(
        "ho-untouched",
        conversation_id="conv-untouched",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    freeze_queue_clock(monkeypatch, BASE)

    with api_client() as api:
        login_employee(api, "agent_1")
        assert queue_items(api)
        login_employee(api, "agent_2")
        assert [item["handoff_id"] for item in queue_items(api)] == ["ho-untouched"]

    handoff = rows_of(ServiceHandoff)[0]
    assert handoff.status == "QUEUED"
    assert handoff.claimed_by is None
    assert handoff.claimed_at is None
    assert handoff.version == 0
    conversation = rows_of(ServiceConversation)[0]
    assert conversation.assigned_employee_id is None


def test_客户转人工后队列出现该交接单_AC_35() -> None:
    with api_client() as api:
        login_customer(api, "customer_a")
        sent = api.post(
            "/customer/messages",
            json={"content": "转人工"},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert sent.status_code == 200, sent.text
        assert sent.json()["status"] == "QUEUED"

        login_employee(api, "agent_1")
        items = queue_items(api)

    assert len(items) == 1
    item = items[0]
    assert item["customer_username"] == "customer_a"
    assert item["customer_display_name"] == "客户甲"
    assert item["conversation_id"] == sent.json()["conversation_id"]
    assert item["reason"] == "CUSTOMER_REQUEST"
    # F-28：客户转人工时补查最近订单，队列摘要显示真实订单数（003 AC-55）。
    assert item["order_count"] == 4
    assert item["last_message"] == "转人工"
    assert item["waiting_seconds"] >= 0
