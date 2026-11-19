"""OTel tracecontext 兼容：解析、转换与请求中间件。"""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.api.request_id import attach_request_id
from backend.platform.telemetry import (
    format_traceparent,
    parse_traceparent,
    to_otel_span_id,
    to_otel_trace_id,
)

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def test_解析合法traceparent() -> None:
    parsed = parse_traceparent(TRACEPARENT)
    assert parsed is not None
    trace_id, span_id = parsed
    assert trace_id == "4bf92f35-77b3-4da6-a3ce-929d0e0e4736"
    assert span_id == "00f067aa0ba902b7"


def test_拒绝非法与全零traceparent() -> None:
    assert parse_traceparent(None) is None
    assert parse_traceparent("bad") is None
    assert parse_traceparent("00-" + "0" * 32 + "-" + "00f067aa0ba902b7-01") is None
    assert parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-" + "0" * 16 + "-01") is None


def test_uuid与hex互转() -> None:
    trace_id = "4bf92f35-77b3-4da6-a3ce-929d0e0e4736"
    assert to_otel_trace_id(trace_id) == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert to_otel_span_id("00f067aa0ba902b7") == "00f067aa0ba902b7"
    assert to_otel_span_id("exec-1") == to_otel_span_id("exec-1")
    assert len(to_otel_span_id("exec-1")) == 16
    assert format_traceparent(trace_id, "00f067aa0ba902b7").startswith("00-4bf92f35")


def test_请求中间件透传traceparent() -> None:
    app = FastAPI()
    app.middleware("http")(attach_request_id)

    @app.get("/probe")
    def probe(request: Request) -> dict[str, str | None]:
        return {
            "trace_id": request.state.trace_id,
            "otel_trace_id": request.state.otel_trace_id,
            "parent_span_id": getattr(request.state, "otel_parent_span_id", None),
        }

    response = TestClient(app).get("/probe", headers={"traceparent": TRACEPARENT})

    assert response.status_code == 200
    assert response.json() == {
        "trace_id": "4bf92f35-77b3-4da6-a3ce-929d0e0e4736",
        "otel_trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "parent_span_id": "00f067aa0ba902b7",
    }


def test_非法traceparent回退XRequestID() -> None:
    app = FastAPI()
    app.middleware("http")(attach_request_id)

    @app.get("/probe")
    def probe(request: Request) -> dict[str, str]:
        return {"trace_id": request.state.trace_id}

    response = TestClient(app).get(
        "/probe", headers={"traceparent": "bad", "X-Request-ID": "req-123"}
    )

    assert response.json()["trace_id"] == "req-123"
