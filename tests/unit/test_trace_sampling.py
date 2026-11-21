"""技术 trace 的尾采样与进程内指标。"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.platform import metrics
from backend.platform.observability import SampledTraceSink


class InnerSink:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []

    def start(self, **kwargs: Any) -> str:
        self.started.append(kwargs)
        return "inner-exec"

    def finish(self, execution_id: str, **kwargs: Any) -> None:
        self.finished.append({"execution_id": execution_id, **kwargs})

    def reject(self, **kwargs: Any) -> None:
        self.rejected.append(kwargs)


@pytest.fixture(autouse=True)
def reset_metrics() -> Any:
    metrics.reset()
    yield
    metrics.reset()


def _sink(rate: float) -> tuple[SampledTraceSink, InnerSink]:
    inner = InnerSink()
    return SampledTraceSink(inner, rate), inner


def _start(sink: SampledTraceSink, tool: str = "lookup") -> str:
    return sink.start(
        tool=tool,
        identity=object(),
        order_id="ORD-10001",
        idempotency_key=None,
        trace_id="t-1",
        payload={"order_id": "ORD-10001"},
    )


def test_异常尾采样保留() -> None:
    sink, inner = _sink(0.0)
    token = _start(sink)

    sink.finish(token, result_status="failed", error_code="DEPENDENCY_TIMEOUT")

    assert len(inner.started) == 1
    assert inner.finished[0]["error_code"] == "DEPENDENCY_TIMEOUT"
    assert metrics.snapshot()["trace_sampled_total"] == 1
    assert metrics.snapshot().get("trace_dropped_total") is None


def test_正常成功按采样率丢弃() -> None:
    sink, inner = _sink(0.0)
    token = _start(sink)

    sink.finish(token, result_status="ok")

    assert inner.started == []
    assert metrics.snapshot()["trace_dropped_total"] == 1


def test_正常成功采样率为1时保留() -> None:
    sink, inner = _sink(1.0)
    token = _start(sink)

    sink.finish(token, result_status="ok")

    assert len(inner.started) == 1
    assert metrics.snapshot()["trace_sampled_total"] == 1


def test_关键工具即使低采样率也保留() -> None:
    sink, inner = _sink(0.0)
    token = _start(sink, tool="submit_cancel")

    sink.finish(token, result_status="ok")

    assert len(inner.started) == 1


def test_订单查询工具即使低采样率也保留_AC_57() -> None:
    """订单查询是隐私敏感读：AC-57 要求每次查询都能在 tool_executions 追溯。"""
    sink, inner = _sink(0.0)
    for tool in ("get_order", "list_recent_orders"):
        token = _start(sink, tool=tool)
        sink.finish(token, result_status="ok")

    assert [item["tool"] for item in inner.started] == ["get_order", "list_recent_orders"]


def test_拒绝始终保留() -> None:
    sink, inner = _sink(0.0)

    sink.reject(
        tool="delete_everything",
        identity=object(),
        order_id=None,
        trace_id="t-1",
        error_code="UNKNOWN_TOOL",
        payload={},
    )

    assert len(inner.rejected) == 1
    assert metrics.snapshot()["trace_sampled_total"] == 1


def test_metrics端点输出计数() -> None:
    metrics.increment("trace_write_failures_total", 2)
    metrics.increment("trace_dropped_total", 3)

    response = TestClient(create_app()).get("/metrics")

    assert response.status_code == 200
    assert "trace_write_failures_total 2" in response.text
    assert "trace_dropped_total 3" in response.text
