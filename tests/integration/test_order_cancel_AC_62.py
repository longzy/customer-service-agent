"""F-31：拒绝、过期与关闭聊天后的任务终态（AC-62）。

点“不取消”或超过确认有效期：任务结束且不提交，OMS 写调用 0，列表恢复可取消；
关闭聊天会话：等待确认任务保留，客户仍可在“我的订单”页确认；已进入提交的任务
不因关闭或过期被放弃。
"""

from typing import Any

import pytest

from tests.integration.cancellation_support import (
    api_client,
    cancellation_app,
    confirm_cancellation,
    create_cancellation,
    decline_cancellation,
    default_order_app,
    read_cancellation,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import login

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

ORDERS = "/customer/orders"


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def _created_task(api: Any) -> dict[str, Any]:
    response = create_cancellation(api)
    assert response.status_code == 200, response.text
    return response.json()


def _order_of(listed: Any, order_id: str = "ORD-10001") -> dict[str, Any]:
    [order] = [item for item in listed.json()["orders"] if item["order_id"] == order_id]
    return order


def test_拒绝后任务结束且不提交_AC_62() -> None:
    """点“不取消”只结束任务，OMS 提交为 0；列表恢复可取消。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        response = decline_cancellation(api, created["id"])
        listed = api.get(ORDERS)

    assert response.status_code == 200, response.text
    task = response.json()
    assert task["state"] == "ABANDONED"
    assert task["status_text"] == "未提交（已放弃）"
    assert task["can_confirm"] is False
    assert app.state.oms.calls["submit_cancel"] == 0
    assert app.state.oms.calls["get_cancel_result"] == 0

    [row] = task_rows()
    assert row.state == "ABANDONED"
    assert row.confirmed_at is None
    order = _order_of(listed)
    assert order["cancelable"] is True
    assert not order.get("cancellation")


def test_拒绝重复请求幂等_AC_62() -> None:
    """重复“不取消”返回同一结果，不新增任务、不写 OMS。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        first = decline_cancellation(api, created["id"])
        second = decline_cancellation(api, created["id"])

    assert first.status_code == second.status_code == 200
    assert first.json()["state"] == second.json()["state"] == "ABANDONED"
    assert len(task_rows()) == 1
    assert app.state.oms.calls["submit_cancel"] == 0


def test_过期任务不提交且可重新发起_AC_62() -> None:
    """超过有效期：任务结束、不提交；再次发起得到新任务。"""
    app = cancellation_app(confirm_timeout_minutes=0)
    with api_client(app) as api:
        login(api)
        expired = _created_task(api)
        listed_after_expiry = api.get(ORDERS)
        ended = confirm_cancellation(api, expired["id"])
        restarted = create_cancellation(api)

    assert listed_after_expiry.status_code == 200
    assert not _order_of(listed_after_expiry).get("cancellation")
    assert ended.status_code == 200, ended.text
    assert ended.json()["state"] == "ABANDONED"

    assert restarted.status_code == 200, restarted.text
    assert restarted.json()["id"] != expired["id"]
    assert restarted.json()["state"] == "AWAITING_CONFIRMATION"

    rows = {row.id: row.state for row in task_rows()}
    assert rows[expired["id"]] == "ABANDONED"
    assert rows[restarted.json()["id"]] == "AWAITING_CONFIRMATION"
    assert app.state.oms.calls["submit_cancel"] == 0


def test_关闭聊天会话保留等待确认任务_AC_62() -> None:
    """关闭聊天不结束等待确认任务，客户仍可在订单页确认。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        closed = api.post(
            "/customer/session/close",
            headers={"Idempotency-Key": "close-after-cancel"},
        )
        listed = api.get(ORDERS)
        confirmed = confirm_cancellation(api, created["id"])

    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "CLOSED"
    order = _order_of(listed)
    assert order["cancellation"]["state"] == "AWAITING_CONFIRMATION"
    assert order["cancellation"]["can_confirm"] is True

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "ACCEPTED"
    assert app.state.oms.calls["submit_cancel"] == 1


def test_已提交任务不因关聊天被放弃_AC_62() -> None:
    """已进入提交/已受理的任务不因关闭会话回退为放弃或重新提交。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        created = _created_task(api)
        confirmed = confirm_cancellation(api, created["id"])
        api.post(
            "/customer/session/close",
            headers={"Idempotency-Key": "close-after-submit"},
        )
        refreshed = read_cancellation(api, created["id"])

    assert confirmed.json()["state"] == "ACCEPTED"
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["state"] == "ACCEPTED"
    assert app.state.oms.calls["submit_cancel"] == 1


def test_他人任务拒绝返回404_AC_62() -> None:
    """客户乙拒绝客户甲的任务按查无处理，不改状态。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        created = _created_task(api)
        login(api, "customer_b")
        response = decline_cancellation(api, created["id"])

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND_OR_UNAUTHORIZED"
    [row] = task_rows()
    assert row.state == "AWAITING_CONFIRMATION"
