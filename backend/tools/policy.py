"""取消资格判定：Policy Engine 是唯一权威，不查询 OMS。"""

from backend.domain.cancellation import CancelEligibility, CancelReason
from backend.domain.orders import OrderDetail, OrderStatus, OrderSummary, is_cancelable
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
    # 资格白名单只由 `is_cancelable` 维护；列表按钮的 cancelable 与提交资格同源，
    # 避免新增状态时两处漂移（design 5.2 S-3）。
    if is_cancelable(status):
        return CancelEligibility(
            eligible=True,
            reason_code=CancelReason.UNFULFILLED,
            requires_confirmation=True,
        )
    reason = REASON_BY_STATUS.get(status)
    if reason is None:
        raise DownstreamInvalidResponse(f"未知订单状态：{status}")
    return CancelEligibility(eligible=False, reason_code=reason, requires_confirmation=False)
