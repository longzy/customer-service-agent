"""取消资格判定（AC-04、AC-07）。"""

import pytest

from services.tools.policy import evaluate_eligibility


def order(status: str, cancelable: bool = True) -> dict:
    return {"order_status": status, "cancelable": cancelable}


def test_未发货订单可取消并要求确认_AC_04() -> None:
    result = evaluate_eligibility(order("PAID_UNFULFILLED"))
    assert result.eligible is True
    assert result.reason_code == "UNFULFILLED"
    assert result.requires_confirmation is True


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("FULFILLING", "FULFILLING"),
        ("SHIPPED", "SHIPPED"),
        ("DELIVERED", "DELIVERED"),
        ("CANCELLED", "CANCELLED"),
    ],
)
def test_不可取消状态返回原因码_AC_07(status: str, reason: str) -> None:
    result = evaluate_eligibility(order(status))
    assert result.eligible is False
    assert result.reason_code == reason
    assert result.requires_confirmation is False


def test_状态与cancelable不一致时以状态为准_AC_07() -> None:
    result = evaluate_eligibility(order("SHIPPED", cancelable=True))
    assert result.eligible is False
    assert result.reason_code == "SHIPPED"


def test_未知状态被拒绝_AC_04() -> None:
    with pytest.raises(ValueError):
        evaluate_eligibility(order("UNKNOWN"))
