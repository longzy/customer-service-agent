"""F-07：队列条件领取（AC-35）。

- 领取是条件写：只有 `QUEUED` 交接单能被领取，并发时恰好一个请求成功，其余 409。
- 领取同事务写会话归属：`status='CLAIMED'`、`assigned_employee_id=me`。
- 跨租户/不存在 404；已关闭 409 `CONVERSATION_CLOSED`；未登录 401、非坐席 403。
- 领取只作用于指定交接单，不自动分配其他单。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.platform.models import ServiceConversation, ServiceHandoff
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


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client() -> TestClient:
    return TestClient(create_app())


def freeze_claim_clock(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(
        "backend.conversations.workspace_conversations.utc_now",
        lambda: moment,
    )


def claim(api: TestClient, handoff_id: str) -> Any:
    return api.post(CLAIM.format(handoff_id=handoff_id))


def handoff_of(handoff_id: str) -> ServiceHandoff:
    return next(row for row in rows_of(ServiceHandoff) if row.id == handoff_id)


def conversation_of(conversation_id: str) -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def test_领取成功归属本人且队列移除_AC_35(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_claim_clock(monkeypatch, BASE)
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = claim(api, "ho-1")
        assert response.status_code == 200, response.text
        assert response.json() == {
            "handoff_id": "ho-1",
            "conversation_id": "conv-1",
            "status": "CLAIMED",
        }
        assert api.get("/workspace/queue").json()["items"] == []
        conversation_response = api.get("/workspace/conversations/conv-1")
        assert conversation_response.status_code == 200
        assert conversation_response.json()["status"] == "CLAIMED"

    handoff = handoff_of("ho-1")
    assert handoff.status == "CLAIMED"
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.claimed_at == BASE
    assert handoff.version == 1
    conversation = conversation_of("conv-1")
    assert conversation.status == "CLAIMED"
    assert conversation.assigned_employee_id == "emp-agent_1"


def test_两个坐席并发领取只有一个成功_AC_35() -> None:
    seed_queued_handoff(
        "ho-race",
        conversation_id="conv-race",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    barrier = threading.Barrier(2)

    def attempt(username: str) -> tuple[str, int, dict[str, Any]]:
        with TestClient(create_app()) as api:
            login_employee(api, username)
            barrier.wait(timeout=10)
            response = claim(api, "ho-race")
            return username, response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("agent_1", "agent_2")))

    statuses = sorted(status for _, status, _ in results)
    assert statuses == [200, 409], results
    winner = next(username for username, status, _ in results if status == 200)
    conflict = next(body for _, status, body in results if status == 409)
    assert conflict["code"] == "CLAIM_CONFLICT"
    assert conflict["visible"] is True

    handoff = handoff_of("ho-race")
    assert handoff.status == "CLAIMED"
    assert handoff.claimed_by == f"emp-{winner}"
    assert handoff.version == 1
    conversation = conversation_of("conv-race")
    assert conversation.status == "CLAIMED"
    assert conversation.assigned_employee_id == f"emp-{winner}"


def test_第二个坐席领取已领取单409且归属不变_AC_35() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        assert claim(api, "ho-1").status_code == 200
        login_employee(api, "agent_2")
        response = claim(api, "ho-1")

    assert response.status_code == 409
    assert response.json()["code"] == "CLAIM_CONFLICT"
    handoff = handoff_of("ho-1")
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.claimed_at is not None
    assert handoff.version == 1
    conversation = conversation_of("conv-1")
    assert conversation.assigned_employee_id == "emp-agent_1"


def test_同一坐席重复领取409_AC_35(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_claim_clock(monkeypatch, BASE)
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        assert claim(api, "ho-1").status_code == 200
        repeated = claim(api, "ho-1")

    assert repeated.status_code == 409
    assert repeated.json()["code"] == "CLAIM_CONFLICT"
    handoff = handoff_of("ho-1")
    assert handoff.claimed_at == BASE
    assert handoff.version == 1


def test_跨租户与不存在交接单领取404_AC_35() -> None:
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
        created_at=BASE,
        tenant_id="tenant-b",
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        cross_tenant = claim(api, "ho-other-tenant")
        missing = claim(api, "ho-does-not-exist")

    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["code"] == "NOT_FOUND"
    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"
    handoff = handoff_of("ho-other-tenant")
    assert handoff.status == "QUEUED"
    assert handoff.claimed_by is None
    assert handoff.version == 0


def test_未登录401且角色降级后403_AC_35() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
    )

    with api_client() as api:
        anonymous = claim(api, "ho-1")
        login_employee(api, "agent_1")
        set_employee_role("agent_1", "supervisor")
        forbidden = claim(api, "ho-1")

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "SESSION_INVALID"
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"
    assert handoff_of("ho-1").status == "QUEUED"


def test_已关闭交接单领取返回409会话已结束_AC_35() -> None:
    seed_queued_handoff(
        "ho-closed",
        conversation_id="conv-closed",
        customer_id="cust-customer_a",
        status="CLOSED",
        conversation_status="CLOSED",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = claim(api, "ho-closed")

    assert response.status_code == 409
    assert response.json()["code"] == "CONVERSATION_CLOSED"
    handoff = handoff_of("ho-closed")
    assert handoff.status == "CLOSED"
    assert handoff.claimed_by is None
    assert handoff.version == 0


def test_会话状态分歧时领取409且交接单回滚_AC_35() -> None:
    """交接单 QUEUED 但会话不是 QUEUED（脏状态）：整体回滚，不留半领取。"""
    seed_queued_handoff(
        "ho-inconsistent",
        conversation_id="conv-inconsistent",
        customer_id="cust-customer_a",
        status="QUEUED",
        conversation_status="HUMAN_ACTIVE",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        response = claim(api, "ho-inconsistent")

    assert response.status_code == 409
    assert response.json()["code"] == "CLAIM_CONFLICT"
    handoff = handoff_of("ho-inconsistent")
    assert handoff.status == "QUEUED"
    assert handoff.claimed_by is None
    assert handoff.claimed_at is None
    assert handoff.version == 0
    assert conversation_of("conv-inconsistent").status == "HUMAN_ACTIVE"


def test_领取只影响指定交接单不自动分配_AC_35() -> None:
    seed_queued_handoff(
        "ho-first",
        conversation_id="conv-first",
        customer_id="cust-customer_a",
        created_at=BASE,
    )
    seed_queued_handoff(
        "ho-second",
        conversation_id="conv-second",
        customer_id="cust-customer_b",
        created_at=BASE,
    )

    with api_client() as api:
        login_employee(api, "agent_1")
        assert claim(api, "ho-first").status_code == 200
        remaining = api.get("/workspace/queue").json()["items"]

    assert [item["handoff_id"] for item in remaining] == ["ho-second"]
    untouched = handoff_of("ho-second")
    assert untouched.status == "QUEUED"
    assert untouched.claimed_by is None
    assert untouched.claimed_at is None
    assert untouched.version == 0
    assert conversation_of("conv-second").assigned_employee_id is None
