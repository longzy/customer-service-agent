"""取消资格结果类型（AC-04、AC-07）。"""

import pytest
from pydantic import ValidationError

from backend.domain.cancellation import CancelEligibility


def test_合法资格结果通过_AC_04() -> None:
    result = CancelEligibility(eligible=True, reason_code="UNFULFILLED", requires_confirmation=True)
    assert result.requires_confirmation is True


def test_资格结果必须带原因码_AC_04() -> None:
    with pytest.raises(ValidationError):
        CancelEligibility(eligible=False, reason_code="", requires_confirmation=False)


def test_资格结果拒绝额外字段_AC_07() -> None:
    with pytest.raises(ValidationError):
        CancelEligibility(
            eligible=True, reason_code="UNFULFILLED", requires_confirmation=False, extra="x"
        )
