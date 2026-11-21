"""F-26：最近订单列表与订单意图（AC-50）。"""

from typing import Any

import pytest

from backend.conversations.order_queries import RECENT_EMPTY_REPLY
from backend.platform.models import ServiceAiEvent, ServiceHandoff
from tests.integration.customer_support import (
    cleanup_customer_db,
    prepare_customer_db,
    rows_of,
)
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import (
    ai_messages,
    api_client,
    login,
    order_app,
    send,
    unbind_customer,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

MY_ORDERS = {"intent": "QUERY_RECENT", "confidence": 0.95, "reply": "好的。"}
RECENT_PURCHASE = {"intent": "QUERY_ORDER", "confidence": 0.92, "reply": "好的。"}


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def order_query_events() -> list[tuple[str, str, str]]:
    return [
        (event.event_type, event.name, event.status)
        for event in rows_of(ServiceAiEvent)
        if event.event_type == "order_query"
    ]


def test_问我的订单列出最近订单_AC_50() -> None:
    app = order_app({"我的订单": MY_ORDERS})
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "我的订单")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert "最近 4 笔订单" in message["content"]
        assert "2026-11-11 11:00" in message["content"]
        assert "¥699.00" in message["content"]

        orders = message["payload"]["orders"]
        assert [order["order_id"] for order in orders] == [
            "ORD-10002",
            "ORD-10001",
            "ORD-10003",
            "ORD-10004",
        ]
        assert [order["status_label"] for order in orders] == [
            "备货中",
            "已支付未发货",
            "已发货",
            "已取消",
        ]
        assert all("items" not in order for order in orders)

        # 3s 轮询同样带快照，不重新查 OMS
        polled = api.get("/customer/messages", params={"after_id": 0})
        assert polled.status_code == 200
        assert polled.json()["messages"][-1]["payload"]["orders"][0]["order_id"] == "ORD-10002"

    assert rows_of(ServiceHandoff) == []
    assert app.state.oms.calls["list_recent_orders"] == 1
    assert app.state.oms.calls["get_order"] == 0
    assert order_query_events() == [("order_query", "list_recent_orders", "ok")]


def test_模型订单意图但未提订单号也查最近订单_AC_50() -> None:
    app = order_app({"最近买了什么": RECENT_PURCHASE})
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "最近买了什么")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert len(message["payload"]["orders"]) == 4

    assert app.state.oms.calls["list_recent_orders"] == 1
    assert rows_of(ServiceHandoff) == []


def test_无订单明确告知且不建单_AC_50() -> None:
    unbind_customer("customer_a")
    app = order_app({"我的订单": MY_ORDERS})
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "我的订单")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"] == RECENT_EMPTY_REPLY
        assert message["payload"]["orders"] == []

    assert app.state.oms.calls["list_recent_orders"] == 0
    assert rows_of(ServiceHandoff) == []
    assert order_query_events() == [("order_query", "list_recent_orders", "not_found")]


def test_低置信订单意图不触发查询_AC_50() -> None:
    """低置信仍是 001 的转人工路径；订单意图不能绕过置信度门禁。"""
    app = order_app({"我的订单": {"intent": "QUERY_RECENT", "confidence": 0.59, "reply": "好的。"}})
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "我的订单")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"

    assert app.state.oms.calls["list_recent_orders"] == 0
    [handoff] = rows_of(ServiceHandoff)
    assert handoff.reason == "LOW_CONFIDENCE"
    assert handoff.context["trigger"] == "low_confidence"
