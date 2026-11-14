"""订单状态与可取消性（AC-04、AC-07）。"""

from services.api.domain.orders import OrderStatus, is_cancelable


def test_仅未发货订单可取消() -> None:
    assert is_cancelable(OrderStatus.PAID_UNFULFILLED) is True
    assert is_cancelable(OrderStatus.FULFILLING) is False
    assert is_cancelable(OrderStatus.SHIPPED) is False
    assert is_cancelable(OrderStatus.DELIVERED) is False
    assert is_cancelable(OrderStatus.CANCELLED) is False
