"""订单状态与可取消性（AC-04、AC-07）。"""

import pytest

from backend.domain.orders import OrderStatus, is_cancelable


def test_未发货订单可取消_AC_04() -> None:
    assert is_cancelable(OrderStatus.PAID_UNFULFILLED) is True


@pytest.mark.parametrize(
    "status",
    [OrderStatus.FULFILLING, OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.CANCELLED],
)
def test_其余状态不可取消_AC_07(status: OrderStatus) -> None:
    assert is_cancelable(status) is False
