"""F-26：多单/半截/闲聊的澄清与不查（AC-52）。"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from backend.conversations.order_queries import (
    MULTIPLE_ORDERS_REPLY,
    PARTIAL_ORDER_ID_REPLY,
    RECENT_EMPTY_REPLY,
    UNAVAILABLE_REPLY,
)
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


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def order_events() -> list[tuple[str, str, str]]:
    return [
        (event.event_type, event.name, event.status)
        for event in rows_of(ServiceAiEvent)
        if event.event_type == "order_query"
    ]


def test_多个订单号列候选不替客户选_AC_52() -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "帮我查 ORD-10001 和 ORD-10002")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"].startswith(MULTIPLE_ORDERS_REPLY)
        assert "最近 4 笔订单" in message["content"]
        orders = message["payload"]["orders"]
        assert [order["order_id"] for order in orders] == [
            "ORD-10002",
            "ORD-10001",
            "ORD-10003",
            "ORD-10004",
        ]

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 1
    assert rows_of(ServiceHandoff) == []
    assert order_events() == [("order_query", "list_recent_orders", "ok")]


@pytest.mark.parametrize("content", ["查 ORD-10", "订单号 ORD-", "查 ORD-123456789012345"])
def test_半截或格式错误订单号列候选_AC_52(content: str) -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, content)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"].startswith(PARTIAL_ORDER_ID_REPLY)
        assert len(message["payload"]["orders"]) == 4

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 1
    assert rows_of(ServiceHandoff) == []


def test_候选查询失败只提示重试_AC_52() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="list_recent_orders", times=1))
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "帮我查 ORD-10001 和 ORD-10002")
        assert response.status_code == 200, response.text
        [message] = ai_messages(response.json())
        assert message["content"] == UNAVAILABLE_REPLY
        assert message["payload"]["orders"] == []

    assert app.state.oms.calls["get_order"] == 0
    assert rows_of(ServiceHandoff) == []
    assert order_events() == [("order_query", "list_recent_orders", "timeout")]


def test_候选查询为空时告知无订单_AC_52() -> None:
    unbind_customer("customer_a")
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "帮我查 ORD-10001 和 ORD-10002")
        assert response.status_code == 200, response.text
        [message] = ai_messages(response.json())
        assert message["content"] == RECENT_EMPTY_REPLY
        assert message["payload"]["orders"] == []

    assert app.state.oms.calls["list_recent_orders"] == 0
    assert rows_of(ServiceHandoff) == []
    assert order_events() == [("order_query", "list_recent_orders", "not_found")]


def test_闲聊带订单不查询也不转人工_AC_52() -> None:
    """模型回复里提到“订单”是正常引导，不得因此建单（AC-52）。"""
    reply = "您好，您想查询订单吗？可以发订单号。"
    app = order_app({"订单": {"intent": "UNKNOWN", "confidence": 0.95, "reply": reply}})
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "订单")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"] == reply
        assert message["payload"] is None

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 0
    assert rows_of(ServiceHandoff) == []
    assert order_events() == []


def test_订单意图不能截走取消诉求_AC_52() -> None:
    """正文含取消操作词时，即使模型误判订单意图也不走订单查询，改由取消分支承接。"""
    app = order_app(
        {"取消我的订单": {"intent": "QUERY_RECENT", "confidence": 0.95, "reply": "好的。"}}
    )
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "取消我的订单")
        assert response.status_code == 200, response.text
        body = response.json()

        # 004 修订 001 AC-32：取消由取消分支承接，不再一律转人工，也不返回订单查询结果。
        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"] != "好的。"
        assert message["content"].strip()
        # 无会话快照时列候选，不替客户选单。
        assert message["payload"]["orders"]
        assert not message["payload"].get("cancellation")

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 1
    assert rows_of(ServiceHandoff) == []


def test_模型订单意图不能覆盖快递超范围_AC_52() -> None:
    """确定性超范围词优先于模型订单意图（001 AC-32）。"""
    app = order_app(
        {"我的快递到哪了": {"intent": "QUERY_RECENT", "confidence": 0.95, "reply": "好的。"}}
    )
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "我的快递到哪了")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 0
    [handoff] = rows_of(ServiceHandoff)
    assert handoff.reason == "OUT_OF_SCOPE"
    assert handoff.context["trigger"] == "out_of_scope"


def test_半截订单号含超范围词仍转人工_AC_52() -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "查 ORD-10 的快递")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 0
    [handoff] = rows_of(ServiceHandoff)
    assert handoff.reason == "OUT_OF_SCOPE"


def test_完整订单号含超范围诉求仍转人工_AC_52() -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "查 ORD-10001 的快递")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"

    assert app.state.oms.calls["get_order"] == 0
    [handoff] = rows_of(ServiceHandoff)
    assert handoff.reason == "OUT_OF_SCOPE"
