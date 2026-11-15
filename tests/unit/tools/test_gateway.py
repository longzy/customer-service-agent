"""Tool Gateway：契约校验、身份剥离、归属闸门、错误归一与审计。"""

from typing import Any

import pytest

from services.api.auth import Identity
from services.api.domain.errors import ErrorCode
from services.tools.gateway import (
    DownstreamInvalidResponse,
    GatewayError,
    OwnershipIndex,
    ToolGateway,
    ToolSpec,
)

IDENTITY = Identity("zhang-ming", "user-a1", "tenant-a", "张明")
OTHER_USER = Identity("li-hua", "user-a2", "tenant-a", "李华")
OTHER_TENANT = Identity("wang-qiang", "user-b1", "tenant-b", "王强")


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], Identity]] = []
        self.audits: list[dict[str, Any]] = []

    def ok(self, payload: dict[str, Any], identity: Identity, trace_id: str) -> dict[str, Any]:
        self.calls.append((payload, identity))
        return payload

    def audit(self, event: dict[str, Any]) -> None:
        self.audits.append(event)


def gateway(recorder: Recorder, handler: Any = None, requires_order: bool = True) -> ToolGateway:
    ownership = OwnershipIndex()
    ownership.register("ORD-10001", "tenant-a", "user-a1")
    ownership.register("ORD-10002", "tenant-a", "user-a2")
    return ToolGateway(
        tools=[ToolSpec("get_order", handler or recorder.ok, requires_order=requires_order)],
        ownership=ownership,
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
    assert result["order_id"] == "ORD-10002"


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
    ownership = OwnershipIndex()
    tool = ToolGateway(
        tools=[ToolSpec("list_recent_orders", recorder.ok, requires_order=False)],
        ownership=ownership,
        audit=recorder.audit,
    )
    result = tool.invoke("list_recent_orders", {"limit": 5}, IDENTITY, trace_id="t-1")
    assert result == {"limit": 5}
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


def test_审计失败按失败关闭处理_AC_14() -> None:
    ownership = OwnershipIndex()
    ownership.register("ORD-10001", "tenant-a", "user-a1")

    def broken_audit(event: dict[str, Any]) -> None:
        raise RuntimeError("audit down")

    tool = ToolGateway(
        tools=[ToolSpec("get_order", lambda payload, identity, trace_id: payload)],
        ownership=ownership,
        audit=broken_audit,
    )
    with pytest.raises(GatewayError) as exc:
        tool.invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1")
    assert exc.value.status_code == 500


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
        ownership=OwnershipIndex(),
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
        return payload

    gateway(recorder, handler=handler).invoke(
        "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="trace-9"
    )
    assert seen == ["trace-9"]
