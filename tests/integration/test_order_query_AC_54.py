"""F-26：订单回复只含 OMS 摘要字段（AC-54）。

覆盖单笔与最近订单两条回复路径：不出现 items/SKU/支付附加字段/手机号，
消息 payload 的键集合与白名单一致，状态文案与 GLOSSARY 一致。
"""

import re
from typing import Any

import pytest

from backend.platform.models import ServiceHandoff
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

SUMMARY_KEYS = {
    "order_id",
    "item_summary",
    "order_status",
    "status_label",
    "amount_cents",
    "currency",
    "created_at",
    "created_at_local",
}
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
FABRICATION_TERMS = ("预计", "明天", "物流", "快递", "运单", "签收", "到货")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def test_单笔与列表回复只含摘要字段_AC_54() -> None:
    app = order_app({"我的订单": {"intent": "QUERY_RECENT", "confidence": 0.95, "reply": "好的。"}})
    with api_client(app) as api:
        login(api, "customer_a")
        single = send(api, "查 ORD-10001")
        recent = send(api, "我的订单")
        candidates = send(api, "查 ORD-10001 和 ORD-10002")
        assert single.status_code == 200, single.text
        assert recent.status_code == 200, recent.text
        assert candidates.status_code == 200, candidates.text

        single_ai = ai_messages(single.json())[0]
        recent_ai = ai_messages(recent.json())[0]
        candidates_ai = ai_messages(candidates.json())[0]

    for message in (single_ai, recent_ai, candidates_ai):
        content = message["content"]
        assert "ORD-" in content
        assert "SKU" not in content
        assert "items" not in content
        assert "paid_at" not in content
        assert "shipped_at" not in content
        assert PHONE_PATTERN.search(content) is None
        for term in FABRICATION_TERMS:
            assert term not in content

    single_order = single_ai["payload"]["orders"][0]
    assert set(single_order) == SUMMARY_KEYS
    assert single_order["status_label"] == "已支付未发货"
    assert single_order["amount_cents"] == 39900

    recent_orders = recent_ai["payload"]["orders"]
    assert len(recent_orders) == 4
    for order in recent_orders:
        assert set(order) == SUMMARY_KEYS

    # 多单候选走同一摘要模板，也必须只含白名单字段。
    candidate_orders = candidates_ai["payload"]["orders"]
    assert len(candidate_orders) == 4
    for order in candidate_orders:
        assert set(order) == SUMMARY_KEYS
        assert order["order_status"] in {
            "PAID_UNFULFILLED",
            "FULFILLING",
            "SHIPPED",
            "CANCELLED",
        }
    assert {order["order_id"]: order["status_label"] for order in recent_orders} == {
        "ORD-10001": "已支付未发货",
        "ORD-10002": "备货中",
        "ORD-10003": "已发货",
        "ORD-10004": "已取消",
    }

    assert rows_of(ServiceHandoff) == []
