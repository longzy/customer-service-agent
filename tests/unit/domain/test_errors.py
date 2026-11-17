"""错误码分类与属性（AC-02、AC-11）。"""

import pytest

from backend.domain.errors import ErrorCode, error_spec


def test_越权统一为查无此单_AC_02() -> None:
    spec = error_spec(ErrorCode.NOT_FOUND_OR_UNAUTHORIZED)
    assert spec.retryable is False
    assert spec.visible is True
    assert spec.user_message == "查无此单"


def test_依赖超时可重试_AC_11() -> None:
    assert error_spec(ErrorCode.DEPENDENCY_TIMEOUT).retryable is True
    assert error_spec(ErrorCode.DEPENDENCY_UNAVAILABLE).retryable is True


def test_响应非法表达为未知_AC_11() -> None:
    spec = error_spec(ErrorCode.INVALID_RESPONSE)
    assert spec.visible is True
    assert spec.user_message == "状态未知，正在核实"


def test_内部错误不对用户展示_AC_11() -> None:
    spec = error_spec(ErrorCode.INTERNAL_ERROR)
    assert spec.visible is False
    assert spec.retryable is False


@pytest.mark.parametrize(
    ("code", "retryable", "visible"),
    [
        (ErrorCode.ELIGIBILITY_REJECTED, False, True),
        (ErrorCode.OMS_REJECTED, False, True),
        (ErrorCode.NOT_FOUND_OR_UNAUTHORIZED, False, True),
        (ErrorCode.DEPENDENCY_UNAVAILABLE, True, True),
        (ErrorCode.DEPENDENCY_TIMEOUT, True, True),
        (ErrorCode.INVALID_RESPONSE, True, True),
        (ErrorCode.INTERNAL_ERROR, False, False),
    ],
)
def test_全部错误码属性表_AC_11(code: ErrorCode, retryable: bool, visible: bool) -> None:
    spec = error_spec(code)
    assert (spec.retryable, spec.visible) == (retryable, visible)
    assert spec.user_message
