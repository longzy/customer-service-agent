"""订单详情与商品明细的类型契约（AC-04 的前置数据）。"""

from typing import Any

import pytest
from pydantic import ValidationError

from services.domain.orders import OrderDetail, OrderItem


def item(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sku": "SKU-1",
        "name": "无线耳机",
        "quantity": 1,
        "unit_amount_cents": 39900,
    }
    data.update(overrides)
    return data


def detail(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "order_id": "ORD-10001",
        "item_summary": "无线耳机 × 1",
        "order_status": "PAID_UNFULFILLED",
        "cancelable": True,
        "amount_cents": 39900,
        "currency": "CNY",
        "created_at": "2026-11-14T06:02:00Z",
        "items": [item()],
        "paid_at": "2026-11-14T06:01:00Z",
        "shipped_at": None,
    }
    data.update(overrides)
    return data


def test_合法订单详情通过_AC_04() -> None:
    order = OrderDetail(**detail())
    assert order.items[0].quantity == 1
    assert order.shipped_at is None


def test_商品数量必须为正_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderItem(**item(quantity=0))


def test_订单详情必须包含商品明细_AC_04() -> None:
    data = detail()
    data.pop("items")
    with pytest.raises(ValidationError):
        OrderDetail(**data)


@pytest.mark.parametrize("field", ["paid_at", "shipped_at"])
def test_订单详情的时间字段必须存在且可为空_AC_04(field: str) -> None:
    data = detail()
    data.pop(field)
    with pytest.raises(ValidationError):
        OrderDetail(**data)
