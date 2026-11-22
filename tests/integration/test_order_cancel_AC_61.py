"""F-31：客户确认后只提交一次并收敛结果（AC-61）。

确认校验归属与状态后只提交一次；结果归一到“已受理/已取消/被拒绝”；
已受理不得表述为已取消或退款；已受理后可按 OMS 结果继续推进。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from tests.integration.cancellation_support import (
    api_client,
    cancellation_app,
    confirm_cancellation,
    create_cancellation,
    default_order_app,
    read_cancellation,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import login

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

ORDERS = "/customer/orders"
TENANT = "tenant-a"


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def _created_task(api: Any) -> dict[str, Any]:
    response = create_cancellation(api)
    assert response.status_code == 200, response.text
    return response.json()


def test_确认后只提交一次并归一到已受理_AC_61() -> None:
    """确认写入确认人/来源，只调用一次 OMS 提交；文案不误报已取消或退款。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        response = confirm_cancellation(api, created["id"])

    assert response.status_code == 200, response.text
    task = response.json()
    assert task["state"] == "ACCEPTED"
    assert task["status_text"] == "已受理，等待最终取消结果"
    assert "已取消" not in task["reply"]
    assert "退款" not in task["reply"]
    assert task["confirmed_at"].endswith("Z")
    assert task["confirmation_source"] == "BUTTON"
    assert task["can_confirm"] is False
    assert app.state.oms.calls["submit_cancel"] == 1

    [row] = task_rows()
    assert row.state == "ACCEPTED"
    assert row.confirmed_by_id == "cust-customer_a"
    assert row.confirmed_at is not None
    assert row.confirmation_source == "BUTTON"


def test_重复确认不重复提交_AC_61() -> None:
    """同一任务重复确认返回同一结果，OMS 提交仍只有一次。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        first = confirm_cancellation(api, created["id"])
        second = confirm_cancellation(api, created["id"])

    assert first.status_code == second.status_code == 200
    assert first.json()["state"] == second.json()["state"] == "ACCEPTED"
    assert first.json()["id"] == second.json()["id"]
    assert app.state.oms.calls["submit_cancel"] == 1


def test_已受理后推进到已取消_AC_61() -> None:
    """已受理不是永久终态：按 OMS 结果推进到已取消，列表同步刷新。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        accepted = confirm_cancellation(api, created["id"])
        assert accepted.json()["state"] == "ACCEPTED"

        [row] = task_rows()
        app.state.oms.set_cancel_result(TENANT, row.idempotency_key, "CANCELLED")
        refreshed = read_cancellation(api, created["id"])
        listed = api.get(ORDERS)

    assert refreshed.status_code == 200, refreshed.text
    task = refreshed.json()
    assert task["state"] == "CANCELLED"
    assert task["status_text"] == "已取消"
    assert "退款" not in task["reply"]
    assert "退款" not in task["status_text"]

    [order] = [item for item in listed.json()["orders"] if item["order_id"] == "ORD-10001"]
    assert order["order_status"] == "CANCELLED"
    assert order["status_label"] == "已取消"
    assert order["cancelable"] is False
    # 已取消由 OMS 订单状态表达；列表不再重复回显终态任务。
    assert not order.get("cancellation")
    assert app.state.oms.calls["submit_cancel"] == 1


def test_受理后被拒绝_AC_61() -> None:
    """受理后 OMS 拒绝时推进到被拒绝，不描述为已取消或退款。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        confirm_cancellation(api, created["id"])
        [row] = task_rows()
        app.state.oms.set_cancel_result(TENANT, row.idempotency_key, "REJECTED")
        refreshed = read_cancellation(api, created["id"])

    assert refreshed.status_code == 200, refreshed.text
    task = refreshed.json()
    assert task["state"] == "REJECTED"
    assert task["status_text"] == "取消申请被拒绝"
    assert "已取消" not in task["reply"]
    assert "退款" not in task["reply"]
    assert app.state.oms.calls["submit_cancel"] == 1


def test_提交超时先核实不重复提交_AC_61() -> None:
    """提交回包丢失时按幂等键核实，结果仍是一次提交后的已受理。"""
    app = default_order_app()
    app.state.oms.faults.add(FaultRule(kind="lost_response", tool="submit_cancel", times=1))
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        response = confirm_cancellation(api, created["id"])

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "ACCEPTED"
    assert app.state.oms.calls["submit_cancel"] == 1


def test_他人任务确认返回404_AC_61() -> None:
    """客户乙确认客户甲的任务按查无处理，不触发提交。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        created = _created_task(api)
        login(api, "customer_b")
        response = confirm_cancellation(api, created["id"])

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND_OR_UNAUTHORIZED"
    assert app.state.oms.calls["submit_cancel"] == 0
    [row] = task_rows()
    assert row.state == "AWAITING_CONFIRMATION"


def test_过期确认不提交_AC_61() -> None:
    """确认过期后任务结束，OMS 提交为 0，结果文案说明未提交。"""
    app = cancellation_app(confirm_timeout_minutes=0)
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        assert created["can_confirm"] is False
        response = confirm_cancellation(api, created["id"])

    assert response.status_code == 200, response.text
    task = response.json()
    assert task["state"] == "ABANDONED"
    assert task["status_text"] == "未提交（已放弃）"
    assert "重新发起" in task["reply"]
    assert app.state.oms.calls["submit_cancel"] == 0
    [row] = task_rows()
    assert row.state == "ABANDONED"
    assert row.confirmed_at is None
