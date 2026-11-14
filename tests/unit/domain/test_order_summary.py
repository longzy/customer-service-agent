"""订单摘要的类型约束：金额用整数分，时间必须是带时区的 UTC。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from services.api.domain.orders import OrderSummary


def payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
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


def test_合法订单摘要通过校验() -> None:
    order = OrderSummary(**payload())
    assert order.amount_cents == 39900
    assert order.created_at == datetime(2026, 11, 14, 6, 2, tzinfo=UTC)


def test_金额不得为负() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(amount_cents=-1))


def test_金额必须是整数分() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(amount_cents=399.0))


def test_时间必须带时区() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**payload(created_at="2026-11-14T06:02:00"))


def test_非UTC时间被归一为UTC() -> None:
    order = OrderSummary(**payload(created_at="2026-11-14T14:02:00+08:00"))
    assert order.created_at == datetime(2026, 11, 14, 6, 2, tzinfo=UTC)
