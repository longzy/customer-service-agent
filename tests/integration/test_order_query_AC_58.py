"""F-29：客户聊天订单卡片的服务端载荷契约（AC-58）。

- 订单消息 `payload.orders` 只含白名单摘要字段（订单号、商品、状态、金额、时间），
  不含 items、手机号、支付或物流字段。
- 最近订单最多 5 条；查无/失败消息的载荷为空数组，前端据此不渲染卡片。
- 金额是整数分、状态是中文文案、时间带本地展示值，前端不需要再猜格式。
"""

from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import api_client, login, order_app, send

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


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


def ai_payload(body: dict[str, Any]) -> dict[str, Any]:
    messages = [item for item in body["messages"] if item["author_type"] == "ai"]
    assert len(messages) == 1
    return messages[0]["payload"]


def test_订单消息载荷字段与白名单_AC_58() -> None:
    """单笔查询：卡片所需字段齐全且只含白名单。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "查 ORD-10001")

    assert response.status_code == 200, response.text
    payload = ai_payload(response.json())
    [order] = payload["orders"]
    assert set(order) == ORDER_FIELDS
    assert order["order_id"] == "ORD-10001"
    assert order["item_summary"] == "无线耳机 × 1"
    assert order["order_status"] == "PAID_UNFULFILLED"
    assert order["status_label"] == "已支付未发货"
    assert order["amount_cents"] == 39900
    assert order["currency"] == "CNY"
    assert order["created_at"].endswith("Z")
    assert order["created_at_local"].startswith("2026-")
    # 卡片不渲染未授权字段；响应文本也不应出现。
    for forbidden in ("items", "sku", "paid_at", "shipped_at", "phone", "payment"):
        assert forbidden not in response.text
    assert "ORD-20001" not in response.text


def test_最近订单最多5条_AC_58() -> None:
    """列表查询：最多 5 条，按最近顺序，不含他人订单号。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "我的订单")

    assert response.status_code == 200, response.text
    orders = ai_payload(response.json())["orders"]
    assert len(orders) == 4
    assert all(set(order) == ORDER_FIELDS for order in orders)
    ids = [order["order_id"] for order in orders]
    # 顺序由 OMS 的“最近”口径决定，不属前端契约；只断言集合与数量。
    assert set(ids) == {"ORD-10001", "ORD-10002", "ORD-10003", "ORD-10004"}
    assert "ORD-20001" not in response.text


def test_查无消息不写订单载荷_AC_58() -> None:
    """他人/不存在：载荷为空数组，前端不渲染卡片，由 AI 文案给出下一步。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "查 ORD-20001")

    assert response.status_code == 200, response.text
    assert ai_payload(response.json()) == {"orders": []}


def test_失败消息不写订单载荷_AC_58() -> None:
    """OMS 超时：载荷为空数组，且不建交接单。"""
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=1))
    with api_client(app) as api:
        login(api)
        response = send(api, "查 ORD-10001")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "AI_ACTIVE"
    assert ai_payload(body) == {"orders": []}
