"""取消任务状态及其对外表达。对外表达是本项目的唯一文案来源（AC-16）。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictBool


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


EXPRESSIONS: dict[CancellationState, str] = {
    CancellationState.COLLECTING: "正在确认订单信息",
    CancellationState.AWAITING_CONFIRMATION: "等待您确认",
    CancellationState.ELIGIBILITY_REJECTED: "不可取消，并说明原因",
    CancellationState.SUBMITTING: "正在提交（过渡态，通常不单独展示）",
    CancellationState.SUBMIT_UNKNOWN: "已提交，正在核实受理结果",
    CancellationState.ACCEPTED: "已受理，等待最终取消结果",
    CancellationState.CANCELLED: "已取消",
    CancellationState.REJECTED: "取消申请被拒绝",
    CancellationState.MANUAL_REVIEW: "已转人工处理",
    CancellationState.ABANDONED: "未提交（已放弃）",
}


def state_expression(state: CancellationState) -> str:
    """返回该状态允许对用户展示的表达；缺少映射直接失败，不返回兜底文案。"""
    return EXPRESSIONS[state]


class CancelEligibility(BaseModel):
    """取消资格结果由 Policy Engine 产出，Agent 只能转述。"""

    model_config = ConfigDict(extra="forbid")

    eligible: StrictBool
    reason_code: str = Field(min_length=1)
    requires_confirmation: StrictBool
