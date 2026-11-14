"""pydantic 必须与 Schema 一样拒绝宽松类型转换（AC-11、AC-14）。"""

from typing import Any

import pytest
from pydantic import ValidationError

from services.api.domain.cancellation import CancelEligibility
from services.api.domain.orders import OrderDetail, OrderItem, OrderSummary


def summary(**overrides: Any) -> dict[str, Any]:
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


@pytest.mark.parametrize("value", ["true", 1, 0])
def test_可取消标记只接受布尔_AC_11(value: Any) -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**summary(cancelable=value))


@pytest.mark.parametrize("value", ["1", True, 1.0])
def test_商品数量只接受整数_AC_11(value: Any) -> None:
    with pytest.raises(ValidationError):
        OrderItem(sku="SKU-1", name="无线耳机", quantity=value, unit_amount_cents=39900)


@pytest.mark.parametrize("value", ["true", 1, 0])
def test_资格布尔字段只接受布尔_AC_11(value: Any) -> None:
    with pytest.raises(ValidationError):
        CancelEligibility(eligible=value, reason_code="UNFULFILLED", requires_confirmation=True)
    with pytest.raises(ValidationError):
        CancelEligibility(eligible=True, reason_code="UNFULFILLED", requires_confirmation=value)


def test_订单详情的可取消标记同样严格_AC_07() -> None:
    with pytest.raises(ValidationError):
        OrderDetail(
            **summary(
                order_status="SHIPPED",
                cancelable=True,
                items=[],
                paid_at=None,
                shipped_at=None,
            )
        )
