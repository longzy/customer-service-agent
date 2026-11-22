"""F-30：我的订单独立页面与列表查询（AC-59）。

客户列表只返回本人、同租户、白名单摘要；空/未绑定返回空列表；OMS 失败可重试且
不阻塞聊天；未登录 401；每次请求带 Trace，访问审计 5 分钟去重。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from backend.api.main import create_app
from backend.api.service_audit import reset_view_dedup
from backend.audit import AuditUnavailableError
from backend.platform.models import ServiceAuditEvent
from backend.platform.settings import Settings
from tests.integration.customer_support import (
    cleanup_customer_db,
    prepare_customer_db,
    rows_of,
)
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import (
    api_client,
    login,
    order_app,
    unbind_customer,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

ORDERS = "/customer/orders"
MESSAGES = "/customer/messages"

# 列表 DTO 白名单：003 摘要字段 + 服务端派生的 cancelable。
ORDER_FIELDS = {
    "order_id",
    "item_summary",
    "order_status",
    "status_label",
    "amount_cents",
    "currency",
    "created_at",
    "created_at_local",
    "cancelable",
    # F-31：列表回显进行中的取消任务；字段仍在白名单内。
    "cancellation",
}


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    reset_view_dedup()
    yield
    cleanup_customer_db()
    reset_view_dedup()


def list_events() -> list[ServiceAuditEvent]:
    return [event for event in rows_of(ServiceAuditEvent) if event.entity_type == "order_list"]


def test_客户列表返回本人最近订单_AC_59() -> None:
    """按创建时间倒序、最多 5 笔；cancelable 由订单状态派生。"""
    with api_client(order_app()) as api:
        login(api)
        response = api.get(ORDERS)

    assert response.status_code == 200, response.text
    body = response.json()
    orders = body["orders"]
    assert [order["order_id"] for order in orders] == [
        "ORD-10002",
        "ORD-10001",
        "ORD-10003",
        "ORD-10004",
    ]
    assert [order["cancelable"] for order in orders] == [False, True, False, False]
    assert [order["status_label"] for order in orders] == [
        "备货中",
        "已支付未发货",
        "已发货",
        "已取消",
    ]
    assert all(set(order) == ORDER_FIELDS for order in orders)
    # 他人订单（user-a2）与跨租户订单（tenant-b）都不可见。
    assert "ORD-10005" not in response.text
    assert "ORD-20001" not in response.text
    assert response.headers["X-Request-ID"]


def test_列表只返回白名单摘要_AC_59() -> None:
    """不返回商品明细、支付信息、手机号或内部归属字段。"""
    with api_client(order_app()) as api:
        login(api)
        response = api.get(ORDERS)

    assert response.status_code == 200, response.text
    for forbidden in (
        "items",
        "sku",
        "paid_at",
        "shipped_at",
        "phone",
        "payment",
        "user-a1",
        "tenant-a",
    ):
        assert forbidden not in response.text


def test_无可见订单客户返回空列表_AC_59() -> None:
    """客户乙在 M1 租户下没有可见订单（跨租户）：200 + 空列表。"""
    with api_client(order_app()) as api:
        login(api, "customer_b")
        response = api.get(ORDERS)

    assert response.status_code == 200, response.text
    assert response.json() == {"orders": []}


def test_未绑定oms客户返回空列表_AC_59() -> None:
    """未绑定 OMS 身份不调用网关，按空列表返回（design 3.3）。"""
    unbind_customer("customer_a")
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = api.get(ORDERS)

    assert response.status_code == 200, response.text
    assert response.json() == {"orders": []}
    assert app.state.oms.calls["list_recent_orders"] == 0


def test_未登录访问订单列表返回401_AC_59() -> None:
    with api_client(order_app()) as api:
        response = api.get(ORDERS)

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_INVALID"
    assert "ORD-" not in response.text


def test_列表读取写访问审计且5分钟去重_AC_59() -> None:
    with api_client(order_app()) as api:
        login(api)
        first = api.get(ORDERS)
        second = api.get(ORDERS)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    # 每次请求仍有独立 Trace；审计按 5 分钟窗口只记一条。
    assert first.headers["X-Request-ID"]
    assert second.headers["X-Request-ID"]

    events = list_events()
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "conversation.viewed"
    assert event.actor_type == "customer"
    assert event.actor_id == "cust-customer_a"
    assert event.entity_id == "cust-customer_a"
    assert event.result_status == "viewed"
    assert event.trace_id == first.headers["X-Request-ID"]
    assert event.metadata_redacted["source"] == "customer"


def test_oms失败返回可重试错误且不阻塞聊天_AC_59() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="unavailable", tool="list_recent_orders", times=1))
    with api_client(app) as api:
        login(api)
        failed = api.get(ORDERS)
        messages = api.get(MESSAGES, params={"after_id": 0})

    assert failed.status_code == 503
    assert failed.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert failed.json()["retryable"] is True
    assert messages.status_code == 200, messages.text


def test_oms超时返回超时错误_AC_59() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="list_recent_orders", times=1))
    with api_client(app) as api:
        login(api)
        response = api.get(ORDERS)

    assert response.status_code == 504
    assert response.json()["code"] == "DEPENDENCY_TIMEOUT"
    assert response.json()["retryable"] is True


def test_limit超出范围返回422_AC_59() -> None:
    with api_client(order_app()) as api:
        login(api)
        limited = api.get(ORDERS, params={"limit": 2})
        too_many = api.get(ORDERS, params={"limit": 6})
        zero = api.get(ORDERS, params={"limit": 0})

    assert limited.status_code == 200, limited.text
    assert [order["order_id"] for order in limited.json()["orders"]] == [
        "ORD-10002",
        "ORD-10001",
    ]
    assert too_many.status_code == 422
    assert too_many.json()["code"] == "VALIDATION_ERROR"
    assert zero.status_code == 422


def test_审计失败返回503_AC_59(monkeypatch: pytest.MonkeyPatch) -> None:
    app = order_app()
    with api_client(app) as api:
        login(api)

        async def fail(_record: ServiceAuditEvent) -> None:
            raise AuditUnavailableError

        monkeypatch.setattr(app.state.audit_writer, "record_view", fail)
        response = api.get(ORDERS)

    assert response.status_code == 503
    assert response.json()["code"] == "AUDIT_UNAVAILABLE"


def test_M1关闭时订单路由不挂载_AC_59() -> None:
    active = Settings(environment="development", m1_enabled=False)
    with api_client(create_app(active)) as api:
        response = api.get(ORDERS)

    assert response.status_code == 404
