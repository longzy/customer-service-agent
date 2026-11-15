"""取消任务状态到用户可见表达的映射（AC-16）。"""

from services.api.domain.cancellation import CancellationState, state_expression


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
