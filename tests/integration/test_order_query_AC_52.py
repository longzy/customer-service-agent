"""F-26：多单/半截/闲聊的澄清与不查（AC-52）。"""

from typing import Any

import pytest

from backend.conversations.order_queries import (
    MULTIPLE_ORDERS_REPLY,
    PARTIAL_ORDER_ID_REPLY,
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
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def order_events() -> list[tuple[str, str]]:
    return [
        (event.event_type, event.status)
        for event in rows_of(ServiceAiEvent)
        if event.event_type == "order_query"
    ]


def test_多个订单号先澄清不查oms_AC_52() -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "帮我查 ORD-10001 和 ORD-10002")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"] == MULTIPLE_ORDERS_REPLY
        assert message["payload"] is None

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 0
    assert rows_of(ServiceHandoff) == []
    assert order_events() == []


@pytest.mark.parametrize("content", ["查 ORD-10", "订单号 ORD-", "查 ORD-123456789012345"])
def test_半截或格式错误订单号先澄清_AC_52(content: str) -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, content)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"] == PARTIAL_ORDER_ID_REPLY
        assert message["payload"] is None

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 0
    assert rows_of(ServiceHandoff) == []


def test_闲聊带订单不查询也不转人工_AC_52() -> None:
    app = order_app(
        {"订单": {"intent": "UNKNOWN", "confidence": 0.95, "reply": "您好，请问需要什么帮助？"}}
    )
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "订单")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"] == "您好，请问需要什么帮助？"
        assert message["payload"] is None

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 0
    assert rows_of(ServiceHandoff) == []
    assert order_events() == []


def test_订单意图不能截走取消诉求_AC_52() -> None:
    """正文含取消/退款等操作词时，即使模型误判订单意图也不查询。"""
    app = order_app(
        {"取消我的订单": {"intent": "QUERY_RECENT", "confidence": 0.95, "reply": "好的。"}}
    )
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "取消我的订单")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "QUEUED"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "system"]

    assert app.state.oms.calls["get_order"] == 0
    assert app.state.oms.calls["list_recent_orders"] == 0
    [handoff] = rows_of(ServiceHandoff)
    assert handoff.reason == "OUT_OF_SCOPE"
    assert handoff.context["trigger"] == "out_of_scope"
