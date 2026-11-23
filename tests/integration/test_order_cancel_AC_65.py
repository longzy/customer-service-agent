"""F-33：客户与坐席的取消归属闸门（AC-65）。

客户侧：他人/跨租户/不存在统一“查无此单”，对他人任务的确认/拒绝/刷新同样
不可区分；未登录 401；全过程不建任务、不写 OMS、不泄露存在性。

坐席侧：归属闸门只放行“本人接管会话 + 交接单已核验订单”；他人会话、跨租户、
未核验订单、非人工接管一律返回查无；坐席代客户确认被拒绝（403 语义）。
按 F-33 §2.3 声明的 S-2 seam，坐席侧直接驱动闸门；HTTP 路由与工作台 UI 由 F-36 接入。
"""

import asyncio
from typing import Any

import pytest

from backend.conversations.cancellation_access import (
    CancellationActorKind,
    CancellationForbidden,
    agent_cancellation_scope,
    customer_cancellation_scope,
    ensure_confirmation_allowed,
)
from backend.identity.customer_sessions import Customer
from backend.identity.employee_sessions import Employee
from tests.integration.cancellation_support import (
    api_client,
    confirm_cancellation,
    create_cancellation,
    decline_cancellation,
    default_order_app,
    refresh_cancellation,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_support import with_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import login
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    prepare_workspace_db,
    seed_queued_handoff,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

AGENT = Employee(
    id="emp-agent_1",
    tenant_id="tenant-a",
    username="agent_1",
    display_name="坐席 1",
    role="agent",
)
CUSTOMER = Customer(
    id="cust-customer_a",
    tenant_id="tenant-a",
    username="customer_a",
    display_name="客户甲",
    oms_customer_id="user-a1",
)


@pytest.fixture
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


@pytest.fixture
def demo_workspace() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def _agent_scope(conversation_id: str, order_id: str) -> Any:
    return asyncio.run(
        with_db(lambda db: agent_cancellation_scope(db, AGENT, conversation_id, order_id))
    )


def test_客户取消他人跨租户与不存在订单统一查无_AC_65(demo_customers: Any) -> None:
    """他人/跨租户/不存在三种 404 同体，且不落任务、不写 OMS。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        others = create_cancellation(api, "ORD-10005")
        cross_tenant = create_cancellation(api, "ORD-20001")
        missing = create_cancellation(api, "ORD-99999")

    assert others.status_code == cross_tenant.status_code == missing.status_code == 404
    assert others.json() == cross_tenant.json() == missing.json()
    assert others.json()["code"] == "NOT_FOUND_OR_UNAUTHORIZED"
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0
    assert app.state.oms.calls["get_cancel_result"] == 0


def test_客户对他人任务统一查无且任务不变_AC_65(demo_customers: Any) -> None:
    """确认/拒绝/刷新他人任务与不存在的任务同体；原任务状态不被改写。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        created = create_cancellation(api).json()
        login(api, "customer_b")
        other_confirm = confirm_cancellation(api, created["id"])
        other_decline = decline_cancellation(api, created["id"])
        other_refresh = refresh_cancellation(api, created["id"])
        missing_confirm = confirm_cancellation(api, "task-missing")

    for response in (other_confirm, other_decline, other_refresh):
        assert response.status_code == 404
        assert response.json() == missing_confirm.json()

    [row] = task_rows()
    assert row.id == created["id"]
    assert row.state == "AWAITING_CONFIRMATION"
    assert row.confirmed_at is None
    assert app.state.oms.calls["submit_cancel"] == 0
    assert app.state.oms.calls["get_cancel_result"] == 0


def test_未登录取消入口一律401_AC_65(demo_customers: Any) -> None:
    app = default_order_app()
    with api_client(app) as api:
        responses = [
            create_cancellation(api),
            confirm_cancellation(api, "task-missing"),
            decline_cancellation(api, "task-missing"),
            refresh_cancellation(api, "task-missing"),
        ]

    for response in responses:
        assert response.status_code == 401
        assert response.json()["code"] == "SESSION_INVALID"
    assert task_rows() == []


def test_坐席闸门只放行本人接管会话的已核验订单_AC_65(demo_workspace: Any) -> None:
    """本人接管 + 交接单已核验订单才可发起；其余一律查无。"""
    seed_queued_handoff(
        "ho-own",
        conversation_id="conv-own",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id=AGENT.id,
        context={"order_count": 1, "orders": [{"order_id": "ORD-10001"}]},
    )
    seed_queued_handoff(
        "ho-other",
        conversation_id="conv-other",
        customer_id="cust-extra-1",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id="emp-agent_2",
        context={"order_count": 1, "orders": [{"order_id": "ORD-10001"}]},
    )
    seed_queued_handoff(
        "ho-tenant-b",
        conversation_id="conv-tenant-b",
        customer_id="cust-customer_b",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id=AGENT.id,
        tenant_id="tenant-b",
        context={"order_count": 1, "orders": [{"order_id": "ORD-20001"}]},
    )
    seed_queued_handoff(
        "ho-ai",
        conversation_id="conv-ai",
        customer_id="cust-extra-2",
        status="ACTIVE",
        conversation_status="AI_ACTIVE",
        assigned_employee_id=None,
        context={"order_count": 1, "orders": [{"order_id": "ORD-10001"}]},
    )

    scope = _agent_scope("conv-own", "ORD-10001")
    assert scope is not None
    assert scope.actor_kind is CancellationActorKind.AGENT
    assert scope.tenant_id == "tenant-a"
    assert scope.owner_customer_id == "cust-customer_a"
    assert scope.actor_id == AGENT.id
    assert scope.verified_order_ids == frozenset({"ORD-10001"})

    assert _agent_scope("conv-own", "ORD-10003") is None
    assert _agent_scope("conv-other", "ORD-10001") is None
    assert _agent_scope("conv-tenant-b", "ORD-20001") is None
    assert _agent_scope("conv-ai", "ORD-10001") is None
    assert _agent_scope("conv-missing", "ORD-10001") is None
    assert task_rows() == []


def test_坐席不能代客户确认_AC_65(demo_workspace: Any) -> None:
    """确认闸门只接受客户 actor；坐席 actor 抛 403 语义，客户本人放行。"""
    seed_queued_handoff(
        "ho-own",
        conversation_id="conv-own",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id=AGENT.id,
        context={"order_count": 1, "orders": [{"order_id": "ORD-10001"}]},
    )
    agent_scope = _agent_scope("conv-own", "ORD-10001")
    assert agent_scope is not None
    with pytest.raises(CancellationForbidden):
        ensure_confirmation_allowed(agent_scope)

    customer_scope = customer_cancellation_scope(CUSTOMER)
    assert customer_scope.actor_kind is CancellationActorKind.CUSTOMER
    ensure_confirmation_allowed(customer_scope)
