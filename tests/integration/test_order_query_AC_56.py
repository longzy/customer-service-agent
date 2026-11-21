"""F-28：工作台详情订单区（AC-56）。

详情从交接单快照投影订单区：只显示该客户名下订单、字段白名单；第二坐席
查看仍 404 且与不存在不可区分；订单查询不可用时状态 `failed`，不阻塞消息
读取、接管与关闭。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from backend.platform.models import ServiceHandoff
from tests.integration.customer_support import rows_of
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import api_client, login, order_app, send
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

DETAIL = "/workspace/conversations/{conversation_id}"
CLAIM = "/workspace/queue/{handoff_id}/claim"
TAKEOVER = "/workspace/conversations/{conversation_id}/takeover"
CLOSE = "/workspace/conversations/{conversation_id}/close"
MESSAGES = "/workspace/conversations/{conversation_id}/messages"

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


def test_详情返回交接单订单区_AC_56() -> None:
    """先查单再转人工：详情订单区与交接单快照一致，只含本人订单。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        assert send(api, "查 ORD-10001").json()["status"] == "AI_ACTIVE"
        assert send(api, "转人工").json()["status"] == "QUEUED"
        handoff = only_handoff()
        assert handoff.context["order_count"] == 1

        login_employee(api, "agent_1")
        assert api.post(CLAIM.format(handoff_id=handoff.id)).status_code == 200
        response = api.get(DETAIL.format(conversation_id=handoff.conversation_id))

    assert response.status_code == 200, response.text
    workspace = response.json()["handoff"]
    assert workspace["order_count"] == 1
    assert workspace["order_context_status"] == "ok"
    [order] = workspace["orders"]
    assert order["order_id"] == "ORD-10001"
    assert order["item_summary"] == "无线耳机 × 1"
    assert order["status_label"] == "已支付未发货"
    assert order["amount_cents"] == 39900
    assert order["currency"] == "CNY"
    # 只显示本人订单：不含 customer_b 的订单号。
    assert "ORD-20001" not in response.text


def test_详情订单字段只含白名单_AC_56() -> None:
    """订单区只投影白名单摘要；不返回 items、手机号、支付等未授权字段。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        assert send(api, "转人工").json()["status"] == "QUEUED"
        handoff = only_handoff()
        login_employee(api, "agent_1")
        assert api.post(CLAIM.format(handoff_id=handoff.id)).status_code == 200
        response = api.get(DETAIL.format(conversation_id=handoff.conversation_id))

    assert response.status_code == 200, response.text
    orders = response.json()["handoff"]["orders"]
    assert len(orders) == 4
    assert all(set(order) == ORDER_FIELDS for order in orders)
    for forbidden in ("items", "sku", "paid_at", "shipped_at", "phone", "payment"):
        assert forbidden not in response.text


def test_第二坐席查看详情404_AC_56() -> None:
    """第二坐席查看已领取会话 404，与不存在会话的响应不可区分。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        assert send(api, "转人工").json()["status"] == "QUEUED"
        handoff = only_handoff()

        login_employee(api, "agent_1")
        assert api.post(CLAIM.format(handoff_id=handoff.id)).status_code == 200

        # 同一浏览器切换为第二坐席：esid 被覆盖，详情仍 404。
        login_employee(api, "agent_2")
        other = api.get(DETAIL.format(conversation_id=handoff.conversation_id))
        missing = api.get(DETAIL.format(conversation_id="conv-does-not-exist"))

    assert other.status_code == 404
    assert missing.status_code == 404
    assert other.json() == missing.json()
    assert other.json()["code"] == "NOT_FOUND"


def test_oms异常详情返回failed且生命周期可用_AC_56() -> None:
    """补查失败：详情状态 failed，不阻塞消息读取、接管与关闭。"""
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="unavailable", tool="list_recent_orders", times=1))
    with api_client(app) as api:
        login(api)
        assert send(api, "转人工").json()["status"] == "QUEUED"
        handoff = only_handoff()

        login_employee(api, "agent_1")
        assert api.post(CLAIM.format(handoff_id=handoff.id)).status_code == 200
        detail = api.get(DETAIL.format(conversation_id=handoff.conversation_id))
        assert detail.status_code == 200, detail.text
        workspace = detail.json()["handoff"]
        assert workspace["order_context_status"] == "failed"
        assert workspace["order_count"] == 0
        assert workspace["orders"] == []

        messages = api.get(
            MESSAGES.format(conversation_id=handoff.conversation_id), params={"after_id": 0}
        )
        assert messages.status_code == 200, messages.text

        assert api.post(TAKEOVER.format(conversation_id=handoff.conversation_id)).status_code == 200
        closed = api.post(
            CLOSE.format(conversation_id=handoff.conversation_id),
            headers={"Idempotency-Key": "close-after-oms-failure"},
        )
        assert closed.status_code == 200, closed.text

    assert only_handoff().status == "CLOSED"
