"""跨站写请求防护：校验 Origin 与 Host。

浏览器对跨站写请求一定带 Origin；命令行与内部调用不带。
因此规则是：带 Origin 必须同源或命中白名单，不带则放行。
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request
from starlette.responses import JSONResponse, Response

from backend.api.service_audit import audit_security_event
from backend.domain.errors import ErrorCode

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REJECTION = {"detail": "跨站请求被拒绝"}


def origin_allowed(origin: str, host: str | None, allowed: set[str]) -> bool:
    """同源或显式白名单才算允许；非法 Origin 一律拒绝。"""
    if origin in allowed:
        return True
    if not host:
        return False
    return urlsplit(origin).netloc == host


async def verify_origin(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.method in UNSAFE_METHODS:
        active = request.app.state.settings
        origin = request.headers.get("origin")
        if origin is not None and not origin_allowed(
            origin, request.headers.get("host"), active.allowed_origin_set
        ):
            # plan 5.1：Origin 拒绝也是 403 安全事件；best-effort 审计后再返回。
            await audit_security_event(request, 403, ErrorCode.FORBIDDEN)
            return JSONResponse(status_code=403, content=REJECTION)
    return await call_next(request)
