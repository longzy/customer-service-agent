"""F-25：订单摘要、订单号提取与回复文案的纯函数用例（AC-51）。"""

from datetime import UTC, datetime

import pytest

from backend.conversations.order_queries import (
    NOT_FOUND_REPLY,
    UNAVAILABLE_REPLY,
    build_order_reply,
    extract_order_ids,
    format_amount,
    format_created_at,
    order_summary,
)


def test_extract_order_ids_大小写与去重() -> None:
    assert extract_order_ids("查 ORD-10001") == ["ORD-10001"]
    assert extract_order_ids("ord-10001 和 ORD-10001") == ["ORD-10001"]
    assert extract_order_ids("ORD-10001 与 ORD-10002") == ["ORD-10001", "ORD-10002"]
    assert extract_order_ids("我的订单到哪了") == []


def test_extract_order_ids_不误吞相邻数字() -> None:
    assert extract_order_ids("ORD-1000123456789") == []
    assert extract_order_ids("XORD-10001") == []
    assert extract_order_ids("ORD-10001号") == ["ORD-10001"]


def test_order_summary_只保留白名单字段() -> None:
    summary = order_summary(
        {
            "order_id": "ORD-10001",
            "item_summary": "无线耳机 × 1",
            "order_status": "PAID_UNFULFILLED",
            "amount_cents": 39900,
            "currency": "CNY",
            "created_at": "2026-11-10T02:00:00Z",
            "items": [{"sku": "SKU-1"}],
            "paid_at": "2026-11-10T02:05:00Z",
            "shipped_at": None,
        }
    )
    assert summary == {
        "order_id": "ORD-10001",
        "item_summary": "无线耳机 × 1",
        "order_status": "PAID_UNFULFILLED",
        "status_label": "已支付未发货",
        "amount_cents": 39900,
        "currency": "CNY",
        "created_at": "2026-11-10T02:00:00Z",
        "created_at_local": "2026-11-10 10:00",
    }


def test_format_amount() -> None:
    assert format_amount(39900, "CNY") == "¥399.00"
    assert format_amount(2900, "CNY") == "¥29.00"
    assert format_amount(2900, "USD") == "USD 29.00"


def test_format_created_at_转上海时区() -> None:
    assert format_created_at("2026-11-10T02:00:00Z") == "2026-11-10 10:00"
    # 已带时区的 ISO 也按同一规则转换
    assert format_created_at("2026-11-10T10:00:00+08:00") == "2026-11-10 10:00"


def test_format_created_at_非法输入回退原文() -> None:
    assert format_created_at("not-a-time") == "not-a-time"


def test_build_order_reply_只陈述摘要字段() -> None:
    summary = order_summary(
        {
            "order_id": "ORD-10001",
            "item_summary": "无线耳机 × 1",
            "order_status": "PAID_UNFULFILLED",
            "amount_cents": 39900,
            "currency": "CNY",
            "created_at": "2026-11-10T02:00:00Z",
        }
    )
    reply = build_order_reply(summary)
    assert "ORD-10001" in reply
    assert "无线耳机 × 1" in reply
    assert "已支付未发货" in reply
    assert "¥399.00" in reply
    assert "2026-11-10 10:00" in reply
    assert "SKU" not in reply


def test_固定文案() -> None:
    assert NOT_FOUND_REPLY == "没有查到你名下的这笔订单，请核对订单号，或说「转人工」。"
    assert UNAVAILABLE_REPLY == "订单查询暂时不可用，可以重试，或说「转人工」。"


@pytest.mark.parametrize(
    "status", ["PAID_UNFULFILLED", "FULFILLING", "SHIPPED", "DELIVERED", "CANCELLED"]
)
def test_状态文案齐全(status: str) -> None:
    summary = order_summary(
        {
            "order_id": "ORD-10001",
            "item_summary": "商品 × 1",
            "order_status": status,
            "amount_cents": 100,
            "currency": "CNY",
            "created_at": "2026-11-10T02:00:00Z",
        }
    )
    assert summary["status_label"] != status


def test_未知状态原样回显() -> None:
    summary = order_summary(
        {
            "order_id": "ORD-10001",
            "item_summary": "商品 × 1",
            "order_status": "REFUNDING",
            "amount_cents": 100,
            "currency": "CNY",
            "created_at": "2026-11-10T02:00:00Z",
        }
    )
    assert summary["status_label"] == "REFUNDING"


def test_时间解析不依赖系统时区() -> None:
    # 固定输入，断言的是 Asia/Shanghai 转换，不随 CI 本地时区变化。
    assert format_created_at("2026-11-10T02:00:00Z") == "2026-11-10 10:00"
    assert datetime(2026, 11, 10, 2, tzinfo=UTC).astimezone().tzinfo is not None
