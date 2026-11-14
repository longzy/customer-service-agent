"""错误码分类与属性（AC-02、AC-11）。"""


from services.api.domain.errors import ErrorCode, error_spec


def test_越权统一为查无此单且不可重试() -> None:
    spec = error_spec(ErrorCode.NOT_FOUND_OR_UNAUTHORIZED)
    assert spec.retryable is False
    assert spec.visible is True
    assert spec.user_message == "查无此单"


def test_依赖超时可重试() -> None:
    assert error_spec(ErrorCode.DEPENDENCY_TIMEOUT).retryable is True
    assert error_spec(ErrorCode.DEPENDENCY_UNAVAILABLE).retryable is True


def test_响应非法表达为未知() -> None:
    spec = error_spec(ErrorCode.INVALID_RESPONSE)
    assert spec.visible is True
    assert spec.user_message == "状态未知，正在核实"


def test_内部错误不对用户展示() -> None:
    assert error_spec(ErrorCode.INTERNAL_ERROR).visible is False


def test_每个错误码都有规格() -> None:
    for code in ErrorCode:
        assert error_spec(code).user_message
