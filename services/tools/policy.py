"""取消资格判定：Policy Engine 是唯一权威，不查询 OMS。"""

from typing import Any

from services.api.domain.cancellation import CancelEligibility
from services.api.domain.orders import OrderStatus, is_cancelable

REASON_BY_STATUS: dict[OrderStatus, str] = {
    OrderStatus.FULFILLING: "FULFILLING",
    OrderStatus.SHIPPED: "SHIPPED",
    OrderStatus.DELIVERED: "DELIVERED",
    OrderStatus.CANCELLED: "CANCELLED",
}


def evaluate_eligibility(order: dict[str, Any]) -> CancelEligibility:
    """根据订单事实判定资格；归属由网关负责，不在本函数内。"""
    try:
        status = OrderStatus(order["order_status"])
    except (KeyError, ValueError) as error:
        raise ValueError("订单状态非法，无法判定资格") from error

    if is_cancelable(status):
        return CancelEligibility(
            eligible=True, reason_code="UNFULFILLED", requires_confirmation=True
        )
    return CancelEligibility(
        eligible=False, reason_code=REASON_BY_STATUS[status], requires_confirmation=False
    )
