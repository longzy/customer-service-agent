"""错误码分类。每个错误码都声明是否可重试、是否对用户可见。"""

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    # 业务拒绝
    ELIGIBILITY_REJECTED = "ELIGIBILITY_REJECTED"
    OMS_REJECTED = "OMS_REJECTED"
    # 越权：不区分“不存在”与“无权”，避免探测订单是否存在
    NOT_FOUND_OR_UNAUTHORIZED = "NOT_FOUND_OR_UNAUTHORIZED"
    # 认证、授权与请求边界（M1 客户/员工 API）
    SESSION_INVALID = "SESSION_INVALID"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    AUTH_FAILED = "AUTH_FAILED"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    CONVERSATION_CLOSED = "CONVERSATION_CLOSED"
    # 依赖不可用
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    DEPENDENCY_TIMEOUT = "DEPENDENCY_TIMEOUT"
    # 响应非法
    INVALID_RESPONSE = "INVALID_RESPONSE"
    # 内部错误
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ErrorSpec:
    retryable: bool
    visible: bool
    user_message: str


SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.ELIGIBILITY_REJECTED: ErrorSpec(False, True, "该订单不能取消"),
    ErrorCode.OMS_REJECTED: ErrorSpec(False, True, "订单系统拒绝取消"),
    ErrorCode.NOT_FOUND_OR_UNAUTHORIZED: ErrorSpec(False, True, "查无此单"),
    ErrorCode.SESSION_INVALID: ErrorSpec(False, True, "登录已失效，请重新登录"),
    ErrorCode.SESSION_EXPIRED: ErrorSpec(False, True, "登录已过期，请重新登录"),
    ErrorCode.AUTH_FAILED: ErrorSpec(False, True, "账号或密码不正确"),
    ErrorCode.NOT_FOUND: ErrorSpec(False, True, "未找到"),
    ErrorCode.VALIDATION_ERROR: ErrorSpec(False, True, "请求参数不正确"),
    ErrorCode.RATE_LIMITED: ErrorSpec(True, True, "请求过于频繁，请稍后再试"),
    ErrorCode.CONVERSATION_CLOSED: ErrorSpec(False, True, "会话已结束"),
    ErrorCode.DEPENDENCY_UNAVAILABLE: ErrorSpec(True, True, "服务暂时不可用，请稍后重试"),
    ErrorCode.DEPENDENCY_TIMEOUT: ErrorSpec(True, True, "响应超时，正在重试"),
    ErrorCode.INVALID_RESPONSE: ErrorSpec(True, True, "状态未知，正在核实"),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(False, False, "系统异常，已转人工"),
}


def error_spec(code: ErrorCode) -> ErrorSpec:
    """返回错误码规格；缺少规格直接失败，不提供默认兜底。"""
    return SPECS[code]
