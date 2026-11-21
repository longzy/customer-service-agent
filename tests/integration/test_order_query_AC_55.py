"""F-28：交接单订单上下文（AC-55）。

客户转人工（AI 主动或客户要求）时，交接单带本人最近订单摘要与 `order_count`
（≤5）；无订单时为 0 且不写空摘要；订单查询不可用时状态记 `failed` 且不阻塞
转人工；会话内已有成功查询快照时复用，不重新查 OMS。
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.adapters.oms.faults import FaultRule
from backend.conversations.customer_chat import RETRY_NOTICE
from backend.platform.models import ServiceAiEvent, ServiceHandoff
from tests.integration.customer_support import rows_of
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import (
    api_client,
    bind_customer,
    login,
    order_app,
    send,
)
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

ORDER_FIELDS = {
    "order_id",
    "item_summary",
    "order_status",
    "status_label",
    "amount_cents",
    "currency",
    "created_at",
    "created_at_local",
}


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def only_handoff() -> ServiceHandoff:
    handoffs = rows_of(ServiceHandoff)
    assert len(handoffs) == 1
    return handoffs[0]


def order_events() -> list[ServiceAiEvent]:
    return [row for row in rows_of(ServiceAiEvent) if row.event_type == "order_query"]


def claim(api: TestClient, handoff_id: str) -> Any:
    return api.post(f"/workspace/queue/{handoff_id}/claim")


def detail(api: TestClient, conversation_id: str) -> Any:
    return api.get(f"/workspace/conversations/{conversation_id}")


def test_关键词转人工带最近订单快照_AC_55() -> None:
    """客户直接说“转人工”：无快照时补查一次最近订单，写进交接单与工作台详情。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "转人工")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "QUEUED"
        conversation_id = body["conversation_id"]

        handoff = only_handoff()
        assert handoff.context["order_count"] == 4
        assert handoff.context["order_context_status"] == "ok"
        orders = handoff.context["orders"]
        assert [item["order_id"] for item in orders] == [
            "ORD-10002",
            "ORD-10001",
            "ORD-10003",
            "ORD-10004",
        ]
        # 只含白名单摘要字段，不泄露 items/支付等未授权字段。
        assert all(set(item) == ORDER_FIELDS for item in orders)
        assert app.state.oms.calls["list_recent_orders"] == 1

        login_employee(api, "agent_1")
        assert claim(api, handoff.id).status_code == 200
        response = detail(api, conversation_id)

    assert response.status_code == 200, response.text
    workspace = response.json()["handoff"]
    assert workspace["order_count"] == 4
    assert workspace["order_context_status"] == "ok"
    assert [item["order_id"] for item in workspace["orders"]] == [
        item["order_id"] for item in orders
    ]


def test_先查单再转人工复用快照_AC_55() -> None:
    """会话内已有成功查询快照时直接复用，不重新查最近订单。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        queried = send(api, "查 ORD-10002")
        assert queried.status_code == 200, queried.text
        assert queried.json()["status"] == "AI_ACTIVE"
        assert send(api, "转人工").json()["status"] == "QUEUED"

    handoff = only_handoff()
    assert handoff.context["order_count"] == 1
    assert handoff.context["order_context_status"] == "ok"
    [order] = handoff.context["orders"]
    assert order["order_id"] == "ORD-10002"
    assert order["status_label"] == "备货中"
    # 复用快照不额外调用 OMS 列表查询。
    assert app.state.oms.calls["list_recent_orders"] == 0


def test_无订单客户转人工订单数为0且不写空摘要_AC_55() -> None:
    """未绑定 OMS 身份：订单数为 0，context 不写空 orders，状态 empty。"""
    bind_customer("customer_a", None)
    app = order_app()
    with api_client(app) as api:
        login(api)
        assert send(api, "转人工").json()["status"] == "QUEUED"

    handoff = only_handoff()
    assert handoff.context["order_count"] == 0
    assert handoff.context["order_context_status"] == "empty"
    assert "orders" not in handoff.context
    assert app.state.oms.calls["list_recent_orders"] == 0


def test_补查失败不阻塞转人工_AC_55() -> None:
    """无快照时补查最近订单失败：仍转人工，状态 failed，不写空摘要。"""
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="list_recent_orders", times=1))
    with api_client(app) as api:
        login(api)
        response = send(api, "转人工")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"

    handoff = only_handoff()
    assert handoff.reason == "CUSTOMER_REQUEST"
    assert handoff.context["order_count"] == 0
    assert handoff.context["order_context_status"] == "failed"
    assert "orders" not in handoff.context
    assert [event.status for event in order_events()] == ["timeout"]


def test_订单连续失败转人工不重复查询_AC_55() -> None:
    """连续两次订单失败转人工：已知 OMS 不可用，不再补查，状态 failed。"""
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=2))
    with api_client(app) as api:
        login(api)
        assert send(api, "查 ORD-10001").json()["status"] == "AI_ACTIVE"
        second = send(api, "查 ORD-10001")
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "QUEUED"

    handoff = only_handoff()
    assert handoff.reason == "ORDER_QUERY_FAILURE"
    assert handoff.context["order_count"] == 0
    assert handoff.context["order_context_status"] == "failed"
    assert "orders" not in handoff.context
    # 只保留两次查询失败的事件；转人工本身不再产生第三次订单查询。
    assert [(row.event_type, row.name, row.status) for row in rows_of(ServiceAiEvent)] == [
        ("order_query", "get_order", "timeout"),
        ("order_query", "get_order", "timeout"),
    ]
    assert app.state.oms.calls["list_recent_orders"] == 0


def test_模型失败转人工复用快照不补查_AC_55() -> None:
    """模型连续失败转人工：有快照则带快照，不额外调用订单列表查询。"""

    class ErrorModel:
        async def respond(self, _message: str) -> Any:
            from backend.agent_runtime.model import ModelError

            raise ModelError("down")

    app = order_app()
    app.state.model_client = ErrorModel()
    with api_client(app) as api:
        login(api)
        assert send(api, "查 ORD-10002").json()["status"] == "AI_ACTIVE"
        assert send(api, "你好").json()["messages"][1]["content"] == RETRY_NOTICE
        second = send(api, "还在吗")
        assert second.json()["status"] == "QUEUED"

    handoff = only_handoff()
    assert handoff.reason == "MODEL_UNAVAILABLE"
    assert handoff.context["order_count"] == 1
    assert handoff.context["orders"][0]["order_id"] == "ORD-10002"
    assert app.state.oms.calls["list_recent_orders"] == 0


def test_模型判定转人工无快照标记未查询_AC_55() -> None:
    """AI 主动转人工且会话内没有已查快照：不额外查 OMS，状态 unknown。"""
    app = order_app(
        {"这个问题我不太确定": {"intent": "UNKNOWN", "confidence": 0.42, "reply": "稍后再试。"}}
    )
    with api_client(app) as api:
        login(api)
        response = send(api, "这个问题我不太确定")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"

    handoff = only_handoff()
    assert handoff.reason == "LOW_CONFIDENCE"
    assert handoff.context["order_count"] == 0
    assert handoff.context["order_context_status"] == "unknown"
    assert "orders" not in handoff.context
    assert app.state.oms.calls["list_recent_orders"] == 0
    assert order_events() == []
