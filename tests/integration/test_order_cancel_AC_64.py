"""F-33：不可取消订单的唯一原因与零写（AC-64）。

备货中/已发货/已送达/已取消四种状态各自只给出一个中文原因，不进入可提交状态，
不调用 OMS 写接口，也不把内部原因码透给客户；列表与聊天卡片按同一状态展示。

夹具里没有“已送达”订单（003 的列表断言依赖现有 4 笔），该状态的映射在
Policy/文案层直接断言；其余三种走真实 HTTP 路径。
"""

import json
from typing import Any

import pytest

from backend.domain.cancellation import (
    REASON_TEXT,
    CancellationState,
    CancelReason,
    render_result,
)
from backend.domain.orders import OrderSummary
from backend.tools.policy import evaluate_eligibility
from tests.integration.cancellation_support import (
    api_client,
    create_cancellation,
    default_order_app,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import ai_messages, login, send

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

ORDERS = "/customer/orders"


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


@pytest.mark.parametrize(
    ("order_id", "reason_text"),
    [
        ("ORD-10002", "订单正在备货"),
        ("ORD-10003", "订单已发货"),
        ("ORD-10004", "订单已取消"),
    ],
)
def test_不可取消订单返回唯一原因且零写_AC_64(order_id: str, reason_text: str) -> None:
    """资格拒绝只写任务、不写 OMS；原因单一且不暴露内部原因码。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = create_cancellation(api, order_id)
        listed = api.get(ORDERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order_id"] == order_id
    assert body["state"] == "ELIGIBILITY_REJECTED"
    assert body["status_text"] == "不可取消，并说明原因"
    assert body["reason_text"] == reason_text
    assert body["can_confirm"] is False
    assert "转人工" in body["reply"]
    # 内部原因码只在服务端落库，不出现在对外契约里。
    assert "reason_code" not in body
    assert "FULFILLING" not in json.dumps(body, ensure_ascii=False)
    assert "SHIPPED" not in json.dumps(body, ensure_ascii=False)

    assert app.state.oms.calls["submit_cancel"] == 0
    assert app.state.oms.calls["get_cancel_result"] == 0

    [row] = task_rows()
    assert row.state == "ELIGIBILITY_REJECTED"
    assert row.reason_code is not None
    assert row.confirmed_at is None

    [order] = [item for item in listed.json()["orders"] if item["order_id"] == order_id]
    assert order["cancelable"] is False
    assert order["cancellation"] is None


def test_已送达订单原因唯一_AC_64() -> None:
    """夹具缺“已送达”订单：在该状态的 Policy 与文案出口上验证唯一原因。"""
    order = OrderSummary.model_validate(
        {
            "order_id": "ORD-10003",
            "item_summary": "显示器 × 1",
            "order_status": "DELIVERED",
            "cancelable": False,
            "amount_cents": 129900,
            "currency": "CNY",
            "created_at": "2026-11-08T01:00:00Z",
        }
    )
    eligibility = evaluate_eligibility(order)
    assert eligibility.eligible is False
    assert eligibility.reason_code is CancelReason.DELIVERED
    assert REASON_TEXT[eligibility.reason_code] == "订单已送达"

    copy = render_result(CancellationState.ELIGIBILITY_REJECTED, eligibility.reason_code)
    assert copy.reason_text == "订单已送达"
    assert "订单已送达" in copy.reply
    assert "转人工" in copy.next_step


def test_不可取消订单聊天卡片同一状态_AC_64() -> None:
    """聊天取消分支与列表同源：同一状态、同一原因，仍不写 OMS。"""
    app = default_order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "取消 ORD-10003")

    assert response.status_code == 200, response.text
    [message] = ai_messages(response.json())[-1:]
    payload = message["payload"]
    assert [order["order_id"] for order in payload["orders"]] == ["ORD-10003"]
    assert payload["cancellation"]["state"] == "ELIGIBILITY_REJECTED"
    assert payload["cancellation"]["can_confirm"] is False
    assert "订单已发货" in message["content"]
    assert "转人工" in message["content"]
    assert app.state.oms.calls["submit_cancel"] == 0
    assert app.state.oms.calls["get_cancel_result"] == 0
