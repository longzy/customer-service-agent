"""F-27：订单查询失败分级（AC-53）。

单次 OMS 超时/异常/非法响应只提示重试、不建单、不改会话状态；同一会话
连续两次订单查询失败自动转人工并说明原因；订单失败与模型失败互不计数。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from backend.agent_runtime.model import ModelError
from backend.conversations.customer_chat import RETRY_NOTICE
from backend.conversations.order_queries import (
    ORDER_FAILURE_HANDOFF_NOTICE,
    UNAVAILABLE_REPLY,
)
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceHandoff,
)
from tests.integration.customer_support import (
    cleanup_customer_db,
    prepare_customer_db,
    rows_of,
    simulate_return_to_ai,
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


class ErrorModel:
    """模型始终异常；用于验证订单失败不并入模型失败计数。"""

    async def respond(self, _message: str) -> Any:
        raise ModelError("down")


def events() -> list[ServiceAiEvent]:
    return sorted(rows_of(ServiceAiEvent), key=lambda event: (event.created_at, event.id))


def test_单次oms异常提示重试且不建单_AC_53() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="unavailable", tool="get_order", times=1))
    with api_client(app) as api:
        login(api)
        response = send(api, "查 ORD-10001")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert message["content"] == UNAVAILABLE_REPLY
        assert message["payload"]["orders"] == []

    assert rows_of(ServiceHandoff) == []
    assert rows_of(ServiceConversation)[0].status == "AI_ACTIVE"
    assert [(event.event_type, event.name, event.status) for event in events()] == [
        ("order_query", "get_order", "error")
    ]


def test_连续两次订单超时转人工并说明原因_AC_53() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=2))
    with api_client(app) as api:
        login(api)
        first = send(api, "查 ORD-10001")
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "AI_ACTIVE"
        assert ai_messages(first.json())[0]["content"] == UNAVAILABLE_REPLY

        second = send(api, "查 ORD-10001")
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["status"] == "QUEUED"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "system"]
        assert body["messages"][1]["content"] == ORDER_FAILURE_HANDOFF_NOTICE
        assert ai_messages(body) == []

    handoff = rows_of(ServiceHandoff)[0]
    assert handoff.status == "QUEUED"
    assert handoff.reason == "ORDER_QUERY_FAILURE"
    assert handoff.context["trigger"] == "order_query_failure"
    assert handoff.context["failure_count"] == 2
    assert handoff.context["last_error"] == "DEPENDENCY_UNAVAILABLE"
    assert [(event.event_type, event.status) for event in events()] == [
        ("order_query", "timeout"),
        ("order_query", "timeout"),
    ]
    assert rows_of(ServiceConversation)[0].status == "QUEUED"


def test_连续两次非法响应转人工_AC_53() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="invalid_response", tool="get_order", times=2))
    with api_client(app) as api:
        login(api)
        assert send(api, "查 ORD-10001").json()["status"] == "AI_ACTIVE"
        second = send(api, "查 ORD-10001")
        assert second.json()["status"] == "QUEUED"
        assert second.json()["messages"][1]["content"] == ORDER_FAILURE_HANDOFF_NOTICE

    handoff = rows_of(ServiceHandoff)[0]
    assert handoff.reason == "ORDER_QUERY_FAILURE"
    assert handoff.context["failure_count"] == 2
    assert handoff.context["last_error"] == "INVALID_RESPONSE"
    assert [event.status for event in events()] == ["error", "error"]


def test_连续失败可混合超时与非法响应_AC_53() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=1))
    app.state.oms.faults.add(FaultRule(kind="invalid_response", tool="get_order", times=1))
    with api_client(app) as api:
        login(api)
        assert send(api, "查 ORD-10001").json()["status"] == "AI_ACTIVE"
        second = send(api, "查 ORD-10001")
        assert second.json()["status"] == "QUEUED"

    handoff = rows_of(ServiceHandoff)[0]
    assert handoff.context["failure_count"] == 2
    assert handoff.context["last_error"] == "INVALID_RESPONSE"
    assert [event.status for event in events()] == ["timeout", "error"]


def test_成功查询打断失败计数_AC_53() -> None:
    app = order_app()
    app.state.oms.faults.add(
        FaultRule(kind="timeout", tool="get_order", order_id="ORD-10001", times=1)
    )
    app.state.oms.faults.add(
        FaultRule(kind="timeout", tool="get_order", order_id="ORD-10003", times=1)
    )
    with api_client(app) as api:
        login(api)
        assert send(api, "查 ORD-10001").json()["status"] == "AI_ACTIVE"
        recovered = send(api, "查 ORD-10002")
        assert recovered.json()["status"] == "AI_ACTIVE"
        assert ai_messages(recovered.json())[0]["payload"]["orders"][0]["order_id"] == "ORD-10002"

        third = send(api, "查 ORD-10003")
        assert third.json()["status"] == "AI_ACTIVE"
        assert ai_messages(third.json())[0]["content"] == UNAVAILABLE_REPLY

    assert rows_of(ServiceHandoff) == []
    assert [event.status for event in events()] == ["timeout", "ok", "timeout"]
    assert rows_of(ServiceConversation)[0].status == "AI_ACTIVE"


def test_订单失败不并入模型失败计数_AC_53() -> None:
    """订单失败 1 次后再模型失败 1 次：模型计数仍是 1，不转人工。"""
    app = order_app()
    app.state.model_client = ErrorModel()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=1))
    with api_client(app) as api:
        login(api)
        assert send(api, "查 ORD-10001").json()["status"] == "AI_ACTIVE"
        model_failed = send(api, "你好")
        assert model_failed.json()["status"] == "AI_ACTIVE"
        assert model_failed.json()["messages"][1]["content"] == RETRY_NOTICE

    assert rows_of(ServiceHandoff) == []
    assert [(event.event_type, event.status) for event in events()] == [
        ("order_query", "timeout"),
        ("model", "error"),
    ]


def test_模型失败不并入订单失败计数_AC_53() -> None:
    """模型失败 1 次后订单失败 2 次：交接单 failure_count 仍是 2。"""
    app = order_app()
    app.state.model_client = ErrorModel()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=2))
    with api_client(app) as api:
        login(api)
        assert send(api, "你好").json()["messages"][1]["content"] == RETRY_NOTICE
        first = send(api, "查 ORD-10001")
        assert first.json()["status"] == "AI_ACTIVE"
        assert ai_messages(first.json())[0]["content"] == UNAVAILABLE_REPLY
        second = send(api, "查 ORD-10001")
        assert second.json()["status"] == "QUEUED"

    handoff = rows_of(ServiceHandoff)[0]
    assert handoff.context["failure_count"] == 2
    assert handoff.context["trigger"] == "order_query_failure"
    assert [(event.event_type, event.status) for event in events()] == [
        ("model", "error"),
        ("order_query", "timeout"),
        ("order_query", "timeout"),
    ]


def test_转回AI后订单失败重新计数_AC_53() -> None:
    app = order_app()
    app.state.oms.faults.add(
        FaultRule(kind="timeout", tool="get_order", order_id="ORD-10001", times=4)
    )
    with api_client(app) as api:
        login(api)
        first = send(api, "查 ORD-10001")
        conversation_id = first.json()["conversation_id"]
        assert send(api, "查 ORD-10001").json()["status"] == "QUEUED"
        simulate_return_to_ai(conversation_id)

        # 转回后的首次失败不沿用转回前的计数。
        retry = send(api, "查 ORD-10001")
        assert retry.json()["status"] == "AI_ACTIVE"
        assert ai_messages(retry.json())[0]["content"] == UNAVAILABLE_REPLY
        again = send(api, "查 ORD-10001")
        assert again.json()["status"] == "QUEUED"

    handoffs = sorted(rows_of(ServiceHandoff), key=lambda handoff: handoff.created_at)
    assert len(handoffs) == 2
    assert handoffs[0].status == "CLOSED"
    assert handoffs[0].context["failure_count"] == 2
    assert handoffs[1].status == "QUEUED"
    assert handoffs[1].context["failure_count"] == 2


def test_候选列表连续失败同样转人工_AC_53() -> None:
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="unavailable", tool="list_recent_orders", times=2))
    with api_client(app) as api:
        login(api)
        first = send(api, "查 ORD-10001 和 ORD-10002")
        assert first.json()["status"] == "AI_ACTIVE"
        assert ai_messages(first.json())[0]["content"] == UNAVAILABLE_REPLY
        second = send(api, "查 ORD-10001 和 ORD-10002")
        assert second.json()["status"] == "QUEUED"
        assert second.json()["messages"][1]["content"] == ORDER_FAILURE_HANDOFF_NOTICE

    handoff = rows_of(ServiceHandoff)[0]
    assert handoff.reason == "ORDER_QUERY_FAILURE"
    assert handoff.context["trigger"] == "order_query_failure"
    assert handoff.context["failure_count"] == 2
    assert handoff.context["last_error"] == "DEPENDENCY_UNAVAILABLE"
    assert [(event.name, event.status) for event in events()] == [
        ("list_recent_orders", "error"),
        ("list_recent_orders", "error"),
    ]
