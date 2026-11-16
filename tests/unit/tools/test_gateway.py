"""Tool Gateway：契约校验、身份剥离、归属闸门、错误归一与审计。"""

from typing import Any

import pytest

from services.domain.errors import ErrorCode
from services.identity import Identity
from services.tools.gateway import (
    DownstreamInvalidResponse,
    GatewayError,
    ToolGateway,
    ToolSpec,
    has_identity_fields,
)

IDENTITY = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
OTHER_USER = Identity("li-hua", "user-a2", "tenant-a", "李华", "示例商户 A")
OTHER_TENANT = Identity("wang-qiang", "user-b1", "tenant-b", "王强", "示例商户 B")


DETAIL = {
    "order_id": "ORD-10001",
    "item_summary": "无线耳机 × 1",
    "order_status": "PAID_UNFULFILLED",
    "cancelable": True,
    "amount_cents": 39900,
    "currency": "CNY",
    "created_at": "2026-11-10T02:00:00Z",
    "items": [{"sku": "S", "name": "无线耳机", "quantity": 1, "unit_amount_cents": 39900}],
    "paid_at": "2026-11-10T02:05:00Z",
    "shipped_at": None,
}


class StubOms:
    """只实现 ToolGateway 需要的归属闸门。"""

    def __init__(self, visible: set[tuple[str, str, str]] | None = None) -> None:
        self.visible = visible or set()

    def is_visible(self, access: Any, order_id: str) -> bool:
        return (access.tenant_id, access.user_id, order_id) in self.visible


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], Identity]] = []
        self.audits: list[dict[str, Any]] = []

    def ok(self, payload: dict[str, Any], identity: Identity, trace_id: str) -> dict[str, Any]:
        self.calls.append((payload, identity))
        return DETAIL

    def audit(self, event: dict[str, Any]) -> None:
        self.audits.append(event)


def gateway(recorder: Recorder, handler: Any = None, requires_order: bool = True) -> ToolGateway:
    oms = StubOms(
        {
            ("tenant-a", "user-a1", "ORD-10001"),
            ("tenant-a", "user-a2", "ORD-10002"),
        }
    )
    return ToolGateway(
        tools=[ToolSpec("get_order", handler or recorder.ok, requires_order=requires_order)],
        oms=oms,
        audit=recorder.audit,
    )


def test_白名单外的工具被拒绝_AC_14() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke(
            "delete_everything", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 404
    assert recorder.calls == []
    assert recorder.audits[-1]["error_code"] == "UNKNOWN_TOOL"


@pytest.mark.parametrize(
    "payload",
    [{"order_id": "ORD-10001", "extra": 1}, {"order_id": 1}, {}, {"order_id": ""}],
)
def test_非法输入按契约被拒绝_AC_14(payload: dict[str, Any]) -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke("get_order", payload, IDENTITY, trace_id="t-1")
    assert exc.value.status_code == 422
    assert recorder.calls == []
    assert recorder.audits[-1]["error_code"] == "INVALID_ARGUMENT"


def test_身份字段判定函数_AC_15() -> None:
    assert has_identity_fields({"tenant_id": "x"}) is True
    assert has_identity_fields({"user_id": "x"}) is True
    assert has_identity_fields({"order_id": "ORD-1"}) is False


def test_请求体不得携带身份字段_AC_15() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke(
            "get_order",
            {"order_id": "ORD-10001", "tenant_id": "tenant-b"},
            IDENTITY,
            trace_id="t-1",
        )
    assert exc.value.status_code == 422
    assert recorder.calls == []


def test_同租户他人订单不可见_AC_02() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke("get_order", {"order_id": "ORD-10002"}, IDENTITY, trace_id="t-1")
    assert exc.value.status_code == 404
    assert exc.value.payload["code"] == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value
    assert recorder.calls == []


def test_跨租户订单被拒绝_AC_03() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke(
            "get_order", {"order_id": "ORD-10001"}, OTHER_TENANT, trace_id="t-1"
        )
    assert exc.value.status_code == 404
    assert exc.value.payload["code"] == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value
    assert recorder.calls == []


def test_同租户其他用户可见自己的订单_AC_02() -> None:
    recorder = Recorder()
    result = gateway(recorder).invoke(
        "get_order", {"order_id": "ORD-10002"}, OTHER_USER, trace_id="t-1"
    )
    assert result["order_id"] == DETAIL["order_id"]


def test_合法调用注入可信身份_AC_15() -> None:
    recorder = Recorder()
    gateway(recorder).invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1")
    payload, identity = recorder.calls[0]
    assert identity is IDENTITY
    assert payload["order_id"] == "ORD-10001"
    assert "tenant_id" not in payload
    assert recorder.audits[-1]["trace_id"] == "t-1"


def test_无需归属的工具跳过闸门_AC_14() -> None:
    recorder = Recorder()
    summary = {
        key: DETAIL[key]
        for key in (
            "order_id",
            "item_summary",
            "order_status",
            "cancelable",
            "amount_cents",
            "currency",
            "created_at",
        )
    }

    def list_handler(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        recorder.calls.append((payload, identity))
        return [summary]

    tool = ToolGateway(
        tools=[ToolSpec("list_recent_orders", list_handler, requires_order=False)],
        oms=StubOms(),
        audit=recorder.audit,
    )
    result = tool.invoke("list_recent_orders", {"limit": 5}, IDENTITY, trace_id="t-1")
    assert result[0]["order_id"] == "ORD-10001"
    assert recorder.calls, "无归属工具应执行"


def test_超时按契约声明的错误码归一_AC_14() -> None:
    recorder = Recorder()

    def timeout(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise TimeoutError

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=timeout).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    # get_order 契约未声明 DEPENDENCY_TIMEOUT，回落到 DEPENDENCY_UNAVAILABLE
    assert exc.value.payload["code"] == ErrorCode.DEPENDENCY_UNAVAILABLE.value
    assert recorder.audits[-1]["error_code"] == "DEPENDENCY_UNAVAILABLE"


def test_非法响应归一为未知_AC_14() -> None:
    recorder = Recorder()

    def bad(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise DownstreamInvalidResponse("bad")

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=bad).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.payload["code"] == ErrorCode.INVALID_RESPONSE.value


def test_未知异常不泄漏内部细节_AC_14() -> None:
    recorder = Recorder()

    def boom(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise RuntimeError("secret stack")

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=boom).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 500
    assert exc.value.payload["code"] == ErrorCode.INTERNAL_ERROR.value
    assert exc.value.payload["visible"] is False
    assert "secret" not in str(exc.value.payload)
    assert recorder.audits[-1]["error_code"] == "INTERNAL_ERROR"


def test_审计失败按失败关闭处理_AC_18() -> None:
    def broken_audit(event: dict[str, Any]) -> None:
        raise RuntimeError("audit down")

    tool = ToolGateway(
        tools=[ToolSpec("get_order", lambda payload, identity, trace_id: payload)],
        oms=StubOms({("tenant-a", "user-a1", "ORD-10001")}),
        audit=broken_audit,
    )
    from services.platform.observability import TraceSinkError

    with pytest.raises(TraceSinkError) as exc:
        tool.invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1")
    assert str(exc.value) == "审计写入失败"


@pytest.mark.parametrize("payload", [None, 1, []])
def test_非对象参数被拒绝而不是崩溃_AC_14(payload: object) -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke("get_order", payload, IDENTITY, trace_id="t-1")  # type: ignore[arg-type]
    assert exc.value.status_code == 422
    assert recorder.audits[-1]["error_code"] == "INVALID_ARGUMENT"
    assert recorder.calls == []


def test_声明了超时错误码的工具返回DEPENDENCY_TIMEOUT_AC_14() -> None:
    recorder = Recorder()

    def timeout(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise TimeoutError

    tool = ToolGateway(
        tools=[ToolSpec("list_recent_orders", timeout, requires_order=False)],
        oms=StubOms(),
        audit=recorder.audit,
    )
    with pytest.raises(GatewayError) as exc:
        tool.invoke("list_recent_orders", {"limit": 5}, IDENTITY, trace_id="t-1")
    assert exc.value.payload["code"] == ErrorCode.DEPENDENCY_TIMEOUT.value
    assert recorder.audits[-1]["error_code"] == "DEPENDENCY_TIMEOUT"


def test_非法响应的审计记录错误码_AC_14() -> None:
    recorder = Recorder()

    def bad(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise DownstreamInvalidResponse("bad")

    with pytest.raises(GatewayError):
        gateway(recorder, handler=bad).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert recorder.audits[-1]["error_code"] == "INVALID_RESPONSE"


def test_越权的审计记录错误码_AC_02() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError):
        gateway(recorder).invoke("get_order", {"order_id": "ORD-10002"}, IDENTITY, trace_id="t-1")
    assert recorder.audits[-1]["error_code"] == "NOT_FOUND_OR_UNAUTHORIZED"


def test_缺少trace_id被拒绝_AC_14() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="")
    assert exc.value.payload["code"] == ErrorCode.INTERNAL_ERROR.value
    assert recorder.calls == []


def test_trace_id传递给handler_AC_14() -> None:
    recorder = Recorder()
    seen: list[str] = []

    def handler(payload: dict[str, Any], identity: Identity, trace_id: str) -> dict[str, Any]:
        seen.append(trace_id)
        return DETAIL

    gateway(recorder, handler=handler).invoke(
        "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="trace-9"
    )
    assert seen == ["trace-9"]


def test_返回非法响应被归类为未知_AC_11() -> None:
    recorder = Recorder()

    def bad(payload: dict[str, Any], identity: Identity, trace_id: str) -> dict[str, Any]:
        return {"order_id": "ORD-10001"}

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=bad).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 502
    assert exc.value.payload["code"] == ErrorCode.INVALID_RESPONSE.value
    assert recorder.audits[-1]["error_code"] == "INVALID_RESPONSE"


def _assert_audit(recorder: Recorder, **overrides: Any) -> None:
    expected: dict[str, Any] = {
        "tool": "get_order",
        "tenant_id": "tenant-a",
        "user_id": "user-a1",
        "order_id": "ORD-10001",
        "result": "ok",
        "error_code": None,
        "trace_id": "t-1",
    }
    expected.update(overrides)
    assert recorder.audits[-1] == expected


def test_成功审计事件字段完整_AC_14() -> None:
    recorder = Recorder()
    gateway(recorder).invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1")
    _assert_audit(recorder)


def test_未知工具审计字段_AC_14() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError):
        gateway(recorder).invoke(
            "delete_everything", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    _assert_audit(
        recorder,
        tool="delete_everything",
        order_id=None,
        result="rejected",
        error_code="UNKNOWN_TOOL",
    )


def test_非法参数审计字段_AC_14() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError):
        gateway(recorder).invoke("get_order", {"order_id": 1}, IDENTITY, trace_id="t-1")
    _assert_audit(recorder, order_id=None, result="rejected", error_code="INVALID_ARGUMENT")


def test_越权审计字段_AC_02() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError):
        gateway(recorder).invoke("get_order", {"order_id": "ORD-10002"}, IDENTITY, trace_id="t-1")
    _assert_audit(
        recorder,
        order_id="ORD-10002",
        result="rejected",
        error_code="NOT_FOUND_OR_UNAUTHORIZED",
    )


def test_超时审计字段_AC_14() -> None:
    recorder = Recorder()

    def timeout(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise TimeoutError

    with pytest.raises(GatewayError):
        gateway(recorder, handler=timeout).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    _assert_audit(recorder, result="failed", error_code="DEPENDENCY_UNAVAILABLE")


def test_非法响应审计字段_AC_11() -> None:
    recorder = Recorder()

    def bad(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise DownstreamInvalidResponse("bad")

    with pytest.raises(GatewayError):
        gateway(recorder, handler=bad).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    _assert_audit(recorder, result="failed", error_code="INVALID_RESPONSE")


def test_未知异常审计字段_AC_14() -> None:
    recorder = Recorder()

    def boom(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise RuntimeError("secret")

    with pytest.raises(GatewayError):
        gateway(recorder, handler=boom).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    _assert_audit(recorder, result="failed", error_code="INTERNAL_ERROR")


def test_响应契约非法审计字段_AC_11() -> None:
    recorder = Recorder()

    def bad(payload: dict[str, Any], identity: Identity, trace_id: str) -> dict[str, Any]:
        return {"order_id": "ORD-10001"}

    with pytest.raises(GatewayError):
        gateway(recorder, handler=bad).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    _assert_audit(recorder, result="failed", error_code="INVALID_RESPONSE")


def test_网关错误保留状态码与消息_AC_14() -> None:
    error = GatewayError(422, {"message": "参数非法"})
    assert error.status_code == 422
    assert error.payload == {"message": "参数非法"}
    assert str(error) == "参数非法"
    assert str(GatewayError(500, {})) == "gateway rejected"


def test_错误封套字段完整_AC_11() -> None:
    from services.domain.errors import SPECS, ErrorCode
    from services.tools.gateway import error_envelope

    for code, spec in SPECS.items():
        assert error_envelope(code) == {
            "code": code.value,
            "retryable": spec.retryable,
            "visible": spec.visible,
            "message": spec.user_message,
        }
    assert error_envelope(ErrorCode.OMS_REJECTED)["message"] == "订单系统拒绝取消"


def test_初始化缺少契约时失败_基座豁免() -> None:
    with pytest.raises(ValueError, match="缺少契约的工具"):
        ToolGateway(
            tools=[ToolSpec("not_in_contract", lambda payload, identity, trace_id: payload)],
            oms=StubOms(),
        )


def test_缺少trace_id的审计字段_AC_14() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError):
        gateway(recorder).invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="")
    _assert_audit(
        recorder,
        order_id=None,
        result="rejected",
        error_code="INTERNAL_ERROR",
        trace_id=None,
    )


def test_未知工具响应体_AC_14() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke(
            "delete_everything", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 404
    assert exc.value.payload == {"message": "未知工具"}


def test_契约校验失败响应体_AC_14() -> None:
    recorder = Recorder()
    with pytest.raises(GatewayError) as exc:
        gateway(recorder).invoke(
            "get_order", {"order_id": "ORD-10001", "extra": 1}, IDENTITY, "t-1"
        )
    assert exc.value.status_code == 422
    assert exc.value.payload == {"message": "参数非法", "errors": 1}


def test_业务拒绝归一与审计_AC_11() -> None:
    from services.errors import CancelRejected

    recorder = Recorder()

    def rejected(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise CancelRejected("no")

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=rejected).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 409
    assert exc.value.payload["code"] == ErrorCode.OMS_REJECTED.value
    _assert_audit(recorder, result="failed", error_code="OMS_REJECTED")


def test_幂等冲突归一与审计_AC_11() -> None:
    from services.errors import IdempotencyConflict

    recorder = Recorder()

    def conflict(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise IdempotencyConflict("conflict")

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=conflict).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 409
    _assert_audit(recorder, result="failed", error_code="OMS_REJECTED")


def test_订单不存在归一与审计_AC_02() -> None:
    from services.errors import OrderNotFound

    recorder = Recorder()

    def missing(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise OrderNotFound("missing")

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=missing).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 404
    _assert_audit(recorder, result="failed", error_code="NOT_FOUND_OR_UNAUTHORIZED")


def test_连接错误归一与审计_AC_11() -> None:
    recorder = Recorder()

    def offline(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise ConnectionError("down")

    with pytest.raises(GatewayError) as exc:
        gateway(recorder, handler=offline).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert exc.value.status_code == 503
    assert exc.value.payload["code"] == ErrorCode.DEPENDENCY_UNAVAILABLE.value
    _assert_audit(recorder, result="failed", error_code="DEPENDENCY_UNAVAILABLE")


class RecordingSink:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []

    def start(self, **kwargs: Any) -> str:
        self.started.append(kwargs)
        return "exec-1"

    def finish(self, execution_id: str, **kwargs: Any) -> None:
        self.finished.append({"execution_id": execution_id, **kwargs})

    def reject(self, **kwargs: Any) -> None:
        self.rejected.append(kwargs)


def test_工具写前与完成审计_AC_17() -> None:
    from services.platform.observability import use_trace_sink

    recorder = Recorder()
    sink = RecordingSink()
    with use_trace_sink(sink):
        gateway(recorder).invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1")
    assert sink.started[0]["tool"] == "get_order"
    assert sink.started[0]["order_id"] == "ORD-10001"
    assert sink.started[0]["trace_id"] == "t-1"
    assert sink.finished[0]["execution_id"] == "exec-1"
    assert sink.finished[0]["result_status"] == "ok"
    assert sink.finished[0]["response"]["order_id"] == "ORD-10001"
    assert sink.finished[0]["latency_ms"] is not None


def test_工具拒绝写审计_AC_17() -> None:
    from services.platform.observability import use_trace_sink

    sink = RecordingSink()
    with use_trace_sink(sink), pytest.raises(GatewayError):
        gateway(Recorder()).invoke(
            "delete_everything", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert sink.rejected[0]["tool"] == "delete_everything"
    assert sink.rejected[0]["error_code"] == "UNKNOWN_TOOL"
    assert sink.rejected[0]["identity"] == IDENTITY
    assert sink.rejected[0]["trace_id"] == "t-1"


def test_工具失败写审计_AC_17() -> None:
    from services.platform.observability import use_trace_sink

    def boom(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise RuntimeError("boom")

    sink = RecordingSink()
    with use_trace_sink(sink), pytest.raises(GatewayError):
        gateway(Recorder(), handler=boom).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert sink.finished[0]["result_status"] == "failed"
    assert sink.finished[0]["error_code"] == "INTERNAL_ERROR"


def test_审计start失败不调用handler_AC_18() -> None:
    from services.platform.observability import TraceSinkError, use_trace_sink

    calls: list[str] = []

    def handler(payload: dict[str, Any], identity: Identity, trace_id: str) -> dict[str, Any]:
        calls.append(trace_id)
        return DETAIL

    class FailingStart(RecordingSink):
        def start(self, **kwargs: Any) -> str:
            raise TraceSinkError("down")

    with use_trace_sink(FailingStart()), pytest.raises(TraceSinkError):
        gateway(Recorder(), handler=handler).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert calls == []


def test_审计finish失败向上抛_AC_18() -> None:
    from services.platform.observability import TraceSinkError, use_trace_sink

    class FailingFinish(RecordingSink):
        def finish(self, execution_id: str, **kwargs: Any) -> None:
            raise TraceSinkError("down")

    with use_trace_sink(FailingFinish()), pytest.raises(TraceSinkError):
        gateway(Recorder()).invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1")


def test_审计reject失败向上抛_AC_18() -> None:
    from services.platform.observability import TraceSinkError, use_trace_sink

    class FailingReject(RecordingSink):
        def reject(self, **kwargs: Any) -> None:
            raise TraceSinkError("down")

    with use_trace_sink(FailingReject()), pytest.raises(TraceSinkError):
        gateway(Recorder()).invoke(
            "delete_everything", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )


def test_非法参数审计sink记录payload_AC_17() -> None:
    from services.platform.observability import use_trace_sink

    sink = RecordingSink()
    with use_trace_sink(sink), pytest.raises(GatewayError):
        gateway(Recorder()).invoke("get_order", {"order_id": 1}, IDENTITY, trace_id="t-1")
    assert sink.rejected[0]["order_id"] is None
    assert sink.rejected[0]["payload"] == {"order_id": 1}
    assert sink.rejected[0]["identity"] == IDENTITY
    assert sink.rejected[0]["trace_id"] == "t-1"


def test_越权审计sink记录payload_AC_17() -> None:
    from services.platform.observability import use_trace_sink

    sink = RecordingSink()
    with use_trace_sink(sink), pytest.raises(GatewayError):
        gateway(Recorder()).invoke("get_order", {"order_id": "ORD-10002"}, IDENTITY, trace_id="t-1")
    assert sink.rejected[0]["order_id"] == "ORD-10002"
    assert sink.rejected[0]["payload"] == {"order_id": "ORD-10002"}
    assert sink.rejected[0]["identity"] == IDENTITY
    assert sink.rejected[0]["trace_id"] == "t-1"


def test_非对象参数审计sink记录空payload_AC_17() -> None:
    from services.platform.observability import use_trace_sink

    sink = RecordingSink()
    with use_trace_sink(sink), pytest.raises(GatewayError):
        gateway(Recorder()).invoke("get_order", 1, IDENTITY, trace_id="t-1")  # type: ignore[arg-type]
    assert sink.rejected[0]["payload"] == {}
