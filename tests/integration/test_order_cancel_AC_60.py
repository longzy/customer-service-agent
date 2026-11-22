"""F-31：列表取消按钮与客户确认（AC-60）。

可取消订单发起取消后只创建任务、停在等待确认，OMS 写调用为 0；不可取消订单
给出唯一原因；他人/不存在订单统一查无；未登录 401；重复点击复用当前任务；
OMS 不可用时返回可重试错误且不创建任务。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from tests.integration.cancellation_support import (
    api_client,
    confirm_cancellation,
    create_cancellation,
    default_order_app,
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


def test_可取消订单进入等待确认且不写oms_AC_60() -> None:
    """创建任务、停在等待确认；确认元信息齐全；OMS 提交/结果调用为 0。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = create_cancellation(api)
        listed = api.get(ORDERS)

    assert response.status_code == 200, response.text
    task = response.json()
    assert task["state"] == "AWAITING_CONFIRMATION"
    assert task["status_text"] == "等待您确认"
    assert task["order_id"] == "ORD-10001"
    assert task["can_confirm"] is True
    assert task["confirmed_at"] is None
    assert task["confirmation_source"] is None
    assert task["expires_at"].endswith("Z")

    # 只有资格查询读了 OMS；没有提交，也没有结果查询。
    assert app.state.oms.calls["submit_cancel"] == 0
    assert app.state.oms.calls["get_cancel_result"] == 0

    rows = task_rows()
    assert len(rows) == 1
    assert rows[0].state == "AWAITING_CONFIRMATION"
    assert rows[0].requested_by_type == "CUSTOMER"
    assert rows[0].requested_by_id == "cust-customer_a"
    assert rows[0].confirmed_at is None

    [order] = [item for item in listed.json()["orders"] if item["order_id"] == "ORD-10001"]
    assert order["cancellation"]["state"] == "AWAITING_CONFIRMATION"
    assert order["cancellation"]["can_confirm"] is True


def test_不可取消订单返回唯一原因且不写oms_AC_60() -> None:
    """备货中/已取消订单不进入可提交状态，原因来自领域文案。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        fulfilling = create_cancellation(api, "ORD-10002")
        cancelled = create_cancellation(api, "ORD-10004")
        listed = api.get(ORDERS)

    assert fulfilling.status_code == 200, fulfilling.text
    body = fulfilling.json()
    assert body["state"] == "ELIGIBILITY_REJECTED"
    assert body["can_confirm"] is False
    assert body["reason_text"] == "订单正在备货"
    assert body["status_text"] == "不可取消，并说明原因"

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["reason_text"] == "订单已取消"

    assert app.state.oms.calls["submit_cancel"] == 0
    assert app.state.oms.calls["get_cancel_result"] == 0
    # 资格拒绝不是进行中的确认，列表不出现待确认入口。
    assert all(not order.get("cancellation") for order in listed.json()["orders"])


def test_他人与不存在订单统一查无_AC_60() -> None:
    """他人/跨租户/不存在都返回同一个 404 封套，不创建任务。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        others = create_cancellation(api, "ORD-10005")
        missing = create_cancellation(api, "ORD-99999")

    assert others.status_code == missing.status_code == 404
    assert others.json() == missing.json()
    assert others.json()["code"] == "NOT_FOUND_OR_UNAUTHORIZED"
    assert task_rows() == []
    assert app.state.oms.calls["submit_cancel"] == 0


def test_重复点击复用当前任务_AC_60() -> None:
    """同一订单已有等待确认任务时不新建，返回同一个任务。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        first = create_cancellation(api)
        second = create_cancellation(api)

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(task_rows()) == 1
    # 第二次直接复用，不再查资格，也不新增 OMS 读调用。
    assert app.state.oms.calls["get_order"] == 1
    assert app.state.oms.calls["submit_cancel"] == 0


def test_未登录创建取消返回401_AC_60() -> None:
    app = default_order_app()
    with api_client(app) as api:
        response = create_cancellation(api)
        confirmed = confirm_cancellation(api, "task-missing")

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_INVALID"
    assert confirmed.status_code == 401
    assert task_rows() == []


def test_oms故障返回可重试错误且不创建任务_AC_60() -> None:
    """资格查询超时/不可用时返回 504/503，不落任务、不写 OMS。"""
    unavailable_app = default_order_app()
    unavailable_app.state.oms.faults.add(FaultRule(kind="unavailable", tool="get_order", times=1))
    timeout_app = default_order_app()
    timeout_app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=1))

    with api_client(unavailable_app) as api:
        login(api)
        unavailable = create_cancellation(api)
    with api_client(timeout_app) as api:
        login(api)
        timed_out = create_cancellation(api)

    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert unavailable.json()["retryable"] is True
    assert timed_out.status_code == 504
    assert timed_out.json()["code"] == "DEPENDENCY_TIMEOUT"
    assert timed_out.json()["retryable"] is True
    assert task_rows() == []
