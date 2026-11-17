"""取消任务状态及其对外表达。对外表达是本项目的唯一文案来源（AC-16）。"""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, StrictBool


class CancellationState(StrEnum):
    COLLECTING = "COLLECTING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    ELIGIBILITY_REJECTED = "ELIGIBILITY_REJECTED"
    SUBMITTING = "SUBMITTING"
    SUBMIT_UNKNOWN = "SUBMIT_UNKNOWN"
    ACCEPTED = "ACCEPTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ABANDONED = "ABANDONED"


class CancelReason(StrEnum):
    UNFULFILLED = "UNFULFILLED"
    FULFILLING = "FULFILLING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class OmsCancelState(StrEnum):
    """OMS 侧只暴露四种结果；Workflow 内部状态不外泄给下游契约。"""

    ACCEPTED = "ACCEPTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


EXPRESSIONS: dict[CancellationState, str] = {
    CancellationState.COLLECTING: "正在确认订单信息",
    CancellationState.AWAITING_CONFIRMATION: "等待您确认",
    CancellationState.ELIGIBILITY_REJECTED: "不可取消，并说明原因",
    CancellationState.SUBMITTING: "正在提交取消申请",
    CancellationState.SUBMIT_UNKNOWN: "已提交，正在核实受理结果",
    CancellationState.ACCEPTED: "已受理，等待最终取消结果",
    CancellationState.CANCELLED: "已取消",
    CancellationState.REJECTED: "取消申请被拒绝",
    CancellationState.MANUAL_REVIEW: "已转人工处理",
    CancellationState.ABANDONED: "未提交（已放弃）",
}

REASON_TEXT: dict[CancelReason, str] = {
    CancelReason.UNFULFILLED: "订单未发货",
    CancelReason.FULFILLING: "订单正在备货",
    CancelReason.SHIPPED: "订单已发货",
    CancelReason.DELIVERED: "订单已送达",
    CancelReason.CANCELLED: "订单已取消",
}

NEXT_STEP: dict[CancellationState, str] = {
    CancellationState.COLLECTING: "请稍候。",
    CancellationState.AWAITING_CONFIRMATION: "请在确认卡片中选择“确认取消”或“不取消”。",
    CancellationState.ELIGIBILITY_REJECTED: "如需进一步处理，可转人工。",
    CancellationState.SUBMITTING: "请稍候，无需重复提交。",
    CancellationState.SUBMIT_UNKNOWN: "如长时间没有结果，可转人工核实。",
    CancellationState.ACCEPTED: "如需帮助，可转人工。",
    CancellationState.CANCELLED: "如需帮助，可转人工。",
    CancellationState.REJECTED: "如需帮助，可转人工。",
    CancellationState.MANUAL_REVIEW: "人工会尽快核实，请稍候。",
    CancellationState.ABANDONED: "如仍需取消，可重新发起。",
}


@dataclass(frozen=True)
class ResultCopy:
    """一个状态的完整结果文案：标签、原因、下一步与整句。"""

    state_text: str
    reason_text: str | None
    next_step: str
    reply: str


def state_expression(state: CancellationState) -> str:
    """返回该状态允许对用户展示的表达；缺少映射直接失败，不返回兜底文案。"""
    return EXPRESSIONS[state]


def render_result(
    state: CancellationState, reason_code: CancelReason | str | None = None
) -> ResultCopy:
    """结果文案的唯一出口；未知状态或缺原因直接失败，不猜测。"""
    if not isinstance(state, CancellationState):
        raise ValueError(f"未知取消状态：{state!r}")
    state_text = state_expression(state)
    reason_text: str | None = None
    base = state_text
    if state is CancellationState.ELIGIBILITY_REJECTED:
        if reason_code is None:
            raise ValueError("ELIGIBILITY_REJECTED 缺少原因码")
        try:
            reason = CancelReason(reason_code)
        except ValueError as error:
            raise ValueError(f"未知取消原因码：{reason_code!r}") from error
        reason_text = REASON_TEXT[reason]
        base = f"{state_text}：{reason_text}"
    next_step = NEXT_STEP[state]
    return ResultCopy(
        state_text=state_text,
        reason_text=reason_text,
        next_step=next_step,
        reply=f"{base}。{next_step}",
    )


class CancelEligibility(BaseModel):
    """取消资格结果由 Policy Engine 产出，Agent 只能转述。"""

    model_config = ConfigDict(extra="forbid")

    eligible: StrictBool
    reason_code: CancelReason
    requires_confirmation: StrictBool
