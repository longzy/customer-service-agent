"""请求关联标识：透传合法 X-Request-ID，缺失或非法时生成。

INV-01 要求每个业务请求都有请求关联标识；后续审计/消息/AI 事件复用同一 id。
"""

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import Response

from backend.platform.telemetry import parse_traceparent, to_otel_trace_id

REQUEST_ID_HEADER = "X-Request-ID"
_VALID = re.compile(r"^[A-Za-z0-9._:-]{1,36}$")


def resolve_request_id(raw: str | None) -> str:
    if raw is not None and _VALID.fullmatch(raw):
        return raw
    return str(uuid.uuid4())


async def attach_request_id(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    incoming = parse_traceparent(request.headers.get("traceparent"))
    if incoming is not None:
        trace_id, parent_span_id = incoming
        request.state.otel_parent_span_id = parent_span_id
    else:
        trace_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.trace_id = trace_id
    request.state.otel_trace_id = to_otel_trace_id(trace_id)
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = trace_id
    return response
