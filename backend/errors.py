"""跨层的下游错误类型。

放在共享模块是为了避免网关与 Mock OMS 各自定义同名异常而无法相互识别。
"""


class OrderNotFound(Exception):
    """订单不存在、不属于当前租户/用户，或不可见；对外统一为“查无此单”。"""


class CancelRejected(Exception):
    """订单当前状态不允许取消（如已发货或已取消）。"""


class IdempotencyConflict(Exception):
    """同一幂等键被用于不同订单。"""


class DownstreamInvalidResponse(Exception):
    """下游返回非法格式，应归类为 INVALID_RESPONSE。"""
