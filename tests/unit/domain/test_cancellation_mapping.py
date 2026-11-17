"""取消任务状态到用户可见表达的映射（AC-16）。"""

import pytest

from backend.domain.cancellation import (
    REASON_TEXT,
    CancellationState,
    CancelReason,
    render_result,
    state_expression,
)


def test_已取消状态表达为已取消_AC_16() -> None:
    assert state_expression(CancellationState.CANCELLED) == "已取消"


EXPECTED = {
    "COLLECTING": "正在确认订单信息",
    "AWAITING_CONFIRMATION": "等待您确认",
    "ELIGIBILITY_REJECTED": "不可取消，并说明原因",
    "SUBMITTING": "正在提交取消申请",
    "SUBMIT_UNKNOWN": "已提交，正在核实受理结果",
    "ACCEPTED": "已受理，等待最终取消结果",
    "CANCELLED": "已取消",
    "REJECTED": "取消申请被拒绝",
    "MANUAL_REVIEW": "已转人工处理",
    "ABANDONED": "未提交（已放弃）",
}


def test_十个取消状态与对外表达一一对应_AC_16() -> None:
    assert {s.value for s in CancellationState} == set(EXPECTED)
    for state in CancellationState:
        assert state_expression(state) == EXPECTED[state.value]


EXPECTED_NEXT_STEP = {
    "COLLECTING": "请稍候。",
    "AWAITING_CONFIRMATION": "请在确认卡片中选择“确认取消”或“不取消”。",
    "ELIGIBILITY_REJECTED": "如需进一步处理，可转人工。",
    "SUBMITTING": "请稍候，无需重复提交。",
    "SUBMIT_UNKNOWN": "如长时间没有结果，可转人工核实。",
    "ACCEPTED": "如需帮助，可转人工。",
    "CANCELLED": "如需帮助，可转人工。",
    "REJECTED": "如需帮助，可转人工。",
    "MANUAL_REVIEW": "人工会尽快核实，请稍候。",
    "ABANDONED": "如仍需取消，可重新发起。",
}

EXPECTED_REASON_TEXT = {
    "UNFULFILLED": "订单未发货",
    "FULFILLING": "订单正在备货",
    "SHIPPED": "订单已发货",
    "DELIVERED": "订单已送达",
    "CANCELLED": "订单已取消",
}

EXPECTED_REPLY = {
    "COLLECTING": "正在确认订单信息。请稍候。",
    "AWAITING_CONFIRMATION": "等待您确认。请在确认卡片中选择“确认取消”或“不取消”。",
    "ELIGIBILITY_REJECTED": "不可取消，并说明原因：订单已发货。如需进一步处理，可转人工。",
    "SUBMITTING": "正在提交取消申请。请稍候，无需重复提交。",
    "SUBMIT_UNKNOWN": "已提交，正在核实受理结果。如长时间没有结果，可转人工核实。",
    "ACCEPTED": "已受理，等待最终取消结果。如需帮助，可转人工。",
    "CANCELLED": "已取消。如需帮助，可转人工。",
    "REJECTED": "取消申请被拒绝。如需帮助，可转人工。",
    "MANUAL_REVIEW": "已转人工处理。人工会尽快核实，请稍候。",
    "ABANDONED": "未提交（已放弃）。如仍需取消，可重新发起。",
}


def test_十个状态的完整回复逐字匹配_AC_16() -> None:
    for name, expected in EXPECTED_REPLY.items():
        state = CancellationState(name)
        reason = CancelReason.SHIPPED if state is CancellationState.ELIGIBILITY_REJECTED else None
        result = render_result(state, reason)
        assert result.state_text == EXPECTED[name]
        assert result.next_step == EXPECTED_NEXT_STEP[name]
        assert result.reply == expected


def test_资格拒绝附带原因文案_AC_16() -> None:
    result = render_result(CancellationState.ELIGIBILITY_REJECTED, CancelReason.SHIPPED)
    assert result.reason_text == "订单已发货"
    assert result.reply == "不可取消，并说明原因：订单已发货。如需进一步处理，可转人工。"


def test_非资格拒绝不展示原因_AC_16() -> None:
    result = render_result(CancellationState.ACCEPTED, CancelReason.SHIPPED)
    assert result.reason_text is None
    assert "原因" not in result.reply


def test_资格拒绝缺原因抛错_AC_16() -> None:
    with pytest.raises(ValueError, match="原因"):
        render_result(CancellationState.ELIGIBILITY_REJECTED, None)


def test_未知原因码抛错_AC_16() -> None:
    with pytest.raises(ValueError, match="原因"):
        render_result(CancellationState.ELIGIBILITY_REJECTED, "NOT_A_REASON")


def test_未知状态抛错_AC_16() -> None:
    with pytest.raises(ValueError, match="状态"):
        render_result("NOT_A_STATE")  # type: ignore[arg-type]


def test_原因码文案完整_AC_16() -> None:
    assert {reason.value for reason in CancelReason} == set(EXPECTED_REASON_TEXT)
    assert {CancelReason(key): value for key, value in EXPECTED_REASON_TEXT.items()} == REASON_TEXT
    for reason, text in EXPECTED_REASON_TEXT.items():
        result = render_result(CancellationState.ELIGIBILITY_REJECTED, reason)
        assert result.reason_text == text
