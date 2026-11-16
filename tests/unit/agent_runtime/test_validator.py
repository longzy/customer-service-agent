"""结果文案校验：逐字通过、漂移替换与失败关闭（AC-10、AC-11、AC-16）。"""

import pytest

from services.agent_runtime.validator import MISMATCH, validate_reply
from services.domain.cancellation import CancellationState, render_result


def test_逐字相等通过_AC_16() -> None:
    expected = render_result(CancellationState.ACCEPTED).reply
    result = validate_reply(CancellationState.ACCEPTED, None, expected)
    assert result.reply == expected
    assert result.replaced is False
    assert result.mismatch is None


def test_草稿漂移替换为权威文案_AC_16() -> None:
    result = validate_reply(CancellationState.ACCEPTED, None, "您的订单已取消")
    assert result.reply == render_result(CancellationState.ACCEPTED).reply
    assert result.replaced is True
    assert result.mismatch == "REPLY_MISMATCH"


def test_空草稿替换为权威文案_AC_16() -> None:
    result = validate_reply(CancellationState.CANCELLED, None, "")
    assert result.reply == render_result(CancellationState.CANCELLED).reply
    assert result.replaced is True


def test_前后空白不视为漂移_AC_16() -> None:
    expected = render_result(CancellationState.CANCELLED).reply
    result = validate_reply(CancellationState.CANCELLED, None, f"  {expected}\n")
    assert result.replaced is False


def test_缺原因抛错_AC_16() -> None:
    with pytest.raises(ValueError, match="原因"):
        validate_reply(CancellationState.ELIGIBILITY_REJECTED, None, "不可取消")


def test_未知状态抛错_AC_16() -> None:
    with pytest.raises(ValueError, match="状态"):
        validate_reply("NOT_A_STATE", None, "任意")  # type: ignore[arg-type]


def test_漂移原因码固定_AC_16() -> None:
    assert MISMATCH == "REPLY_MISMATCH"


def test_重复校验结果一致_AC_16() -> None:
    first = validate_reply(CancellationState.SUBMIT_UNKNOWN, None, "已受理，等待最终取消结果")
    second = validate_reply(CancellationState.SUBMIT_UNKNOWN, None, "已受理，等待最终取消结果")
    assert first == second
    assert first.replaced is True
