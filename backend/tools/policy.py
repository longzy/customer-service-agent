"""取消资格判定：Policy Engine 是唯一权威，不查询 OMS。"""

from backend.domain.cancellation import CancelEligibility, CancelReason
from backend.domain.orders import OrderDetail, OrderStatus, OrderSummary
from backend.errors import DownstreamInvalidResponse

REASON_BY_STATUS: dict[OrderStatus, CancelReason] = {
    OrderStatus.FULFILLING: CancelReason.FULFILLING,
    OrderStatus.SHIPPED: CancelReason.SHIPPED,
    OrderStatus.DELIVERED: CancelReason.DELIVERED,
    OrderStatus.CANCELLED: CancelReason.CANCELLED,
}


def evaluate_eligibility(order: OrderSummary | OrderDetail) -> CancelEligibility:
    """根据领域订单判定资格；归属由网关负责，不在本函数内。"""
    status = order.order_status
    if status == OrderStatus.PAID_UNFULFILLED:
        return CancelEligibility(
            eligible=True,
            reason_code=CancelReason.UNFULFILLED,
            requires_confirmation=True,
        )
    reason = REASON_BY_STATUS.get(status)
    if reason is None:
        raise DownstreamInvalidResponse(f"未知订单状态：{status}")
    return CancelEligibility(eligible=False, reason_code=reason, requires_confirmation=False)
