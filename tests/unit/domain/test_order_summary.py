"""订单摘要的类型约束：金额用整数分，时间必须是带 Z 的 UTC 字符串（AC-04、AC-07）。"""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from backend.domain.orders import OrderSummary


def payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "order_id": "ORD-10001",
        "item_summary": "无线耳机 × 1",
        "order_status": "PAID_UNFULFILLED",
        "cancelable": True,
        "amount_cents": 39900,
        "currency": "CNY",
        "created_at": "2026-11-14T06:02:00Z",
    }
    data.update(overrides)
    return data


def test_合法订单摘要通过校验_AC_04() -> None:
    order = OrderSummary(**payload())
    assert order.amount_cents == 39900
    assert order.created_at == datetime(2026, 11, 14, 6, 2, tzinfo=UTC)


def test_金额不得为负_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(amount_cents=-1))


def test_金额必须是整数分_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(amount_cents=399.0))


def test_时间必须带时区_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(created_at="2026-11-14T06:02:00"))


def test_非UTC偏移被拒绝_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(created_at="2026-11-14T14:02:00+08:00"))


def test_时间戳数字被拒绝_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(created_at=1763100120))


def test_非法时间字符串被拒绝_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(created_at="not-a-date"))


def test_额外字段被拒绝_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(unexpected="x"))


def test_已发货订单不得标记为可取消_AC_07() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(order_status="SHIPPED", cancelable=True))


def test_未发货订单必须标记为可取消_AC_07() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(order_status="PAID_UNFULFILLED", cancelable=False))
