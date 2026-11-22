"""Gateway 的 Trace/审计旁路：成功、失败、拒绝与 sink 自身故障。"""

from typing import Any

import pytest

from backend.identity import Identity
from backend.platform.observability import use_trace_sink
from backend.tools.gateway import GatewayError, ToolGateway, ToolSpec

IDENTITY = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
DETAIL = {
    "order_id": "ORD-10001",
    "item_summary": "无线耳机 × 1",
    "order_status": "PAID_UNFULFILLED",
    "cancelable": True,
    "amount_cents": 39900,
    "currency": "CNY",
    "created_at": "2026-11-10T02:00:00Z",
    "items": [{"sku": "S", "name": "无线耳机", "quantity": 1, "unit_amount_cents": 39900}],
    "paid_at": None,
    "shipped_at": None,
}


class Sink:
    def __init__(self, *, fail_start: bool = False, fail_finish: bool = False) -> None:
        self.fail_start = fail_start
        self.fail_finish = fail_finish
        self.started: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []

    def start(self, **kwargs: Any) -> str:
        if self.fail_start:
            raise RuntimeError("sink start down")
        self.started.append(kwargs)
        return "exec-1"

    def finish(self, execution_id: str, **kwargs: Any) -> None:
        if self.fail_finish:
            raise RuntimeError("sink finish down")
        self.finished.append({"execution_id": execution_id, **kwargs})

    def reject(self, **kwargs: Any) -> None:
        self.rejected.append(kwargs)


class Oms:
    def is_visible(self, access: Any, order_id: str) -> bool:
        return order_id == "ORD-10001"


def tool(handler: Any, *, audit: Any = None) -> ToolGateway:
    return ToolGateway(
        tools=[ToolSpec("get_order", handler)],
        oms=Oms(),
        audit=audit,
    )


def test_成功调用写start与finish_基座豁免() -> None:
    sink = Sink()
    with use_trace_sink(sink):
        result = tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert result == DETAIL
    assert sink.started[0]["tool"] == "get_order"
    assert sink.started[0]["trace_id"] == "t-1"
    assert sink.finished[0]["result_status"] == "ok"
    assert sink.finished[0]["error_code"] is None
    assert sink.finished[0]["response"] == DETAIL
    assert isinstance(sink.finished[0]["latency_ms"], int)


def test_失败调用finish不带响应_基座豁免() -> None:
    sink = Sink()

    def timeout(payload: dict[str, Any], identity: Identity, trace_id: str) -> None:
        raise TimeoutError

    with use_trace_sink(sink), pytest.raises(GatewayError):
        tool(timeout).invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1")
    assert sink.finished[0]["result_status"] == "failed"
    assert sink.finished[0]["error_code"] == "DEPENDENCY_UNAVAILABLE"
    assert sink.finished[0]["response"] is None


def test_拒绝调用写reject_基座豁免() -> None:
    sink = Sink()
    with use_trace_sink(sink), pytest.raises(GatewayError):
        tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "unknown", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert sink.rejected[0]["tool"] == "unknown"
    assert sink.rejected[0]["order_id"] is None
    assert sink.rejected[0]["trace_id"] == "t-1"
    assert sink.rejected[0]["error_code"] == "UNKNOWN_TOOL"


def test_sink_start故障不阻断业务_基座豁免() -> None:
    sink = Sink(fail_start=True)
    with use_trace_sink(sink):
        result = tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert result == DETAIL
    assert sink.finished == []


def test_sink_finish故障不阻断业务_基座豁免() -> None:
    sink = Sink(fail_finish=True)
    with use_trace_sink(sink):
        result = tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
        )
    assert result == DETAIL


def test_未注入审计时调用不崩溃_基座豁免() -> None:
    result = tool(lambda payload, identity, trace_id: DETAIL).invoke(
        "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id="t-1"
    )
    assert result == DETAIL


def test_非对象参数拒绝时记录safe_payload_基座豁免() -> None:
    sink = Sink()
    with use_trace_sink(sink), pytest.raises(GatewayError) as exc:
        tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "get_order",
            None,
            IDENTITY,
            trace_id="t-1",  # type: ignore[arg-type]
        )
    assert exc.value.payload["message"] == "参数非法"
    assert sink.rejected[0]["payload"] == {}
    assert sink.rejected[0]["tool"] == "get_order"
    assert sink.rejected[0]["identity"] == IDENTITY
    assert sink.rejected[0]["order_id"] is None
    assert sink.rejected[0]["trace_id"] == "t-1"
    assert sink.rejected[0]["error_code"] == "INVALID_ARGUMENT"


def test_未知工具拒绝保留safe_payload_基座豁免() -> None:
    sink = Sink()
    payload = {"order_id": "ORD-10001"}
    with use_trace_sink(sink), pytest.raises(GatewayError):
        tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "unknown", payload, IDENTITY, trace_id="t-2"
        )
    assert sink.rejected[0]["payload"] == payload
    assert sink.rejected[0]["error_code"] == "UNKNOWN_TOOL"


def test_身份字段拒绝保留safe_payload_基座豁免() -> None:
    sink = Sink()
    payload = {"order_id": "ORD-10001", "tenant_id": "tenant-b"}
    with use_trace_sink(sink), pytest.raises(GatewayError):
        tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "get_order", payload, IDENTITY, trace_id="t-3"
        )
    assert sink.rejected[0]["payload"] == payload
    assert sink.rejected[0]["error_code"] == "INVALID_ARGUMENT"


def test_空trace_id返回500并记录_基座豁免() -> None:
    sink = Sink()
    with use_trace_sink(sink), pytest.raises(GatewayError) as exc:
        tool(lambda payload, identity, trace_id: DETAIL).invoke(
            "get_order", {"order_id": "ORD-10001"}, IDENTITY, trace_id=""
        )
    assert exc.value.status_code == 500
    assert sink.rejected[0]["trace_id"] == ""
    assert sink.rejected[0]["error_code"] == "INTERNAL_ERROR"
    assert sink.rejected[0]["payload"] == {}
