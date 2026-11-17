"""FastAPI 身份中间件：把服务端会话解析到 request.state。"""

from fastapi import HTTPException, Request

from backend.identity import SESSION_COOKIE, Identity, get_session


async def resolve_identity(request: Request, call_next):  # type: ignore[no-untyped-def]
    """中间件：把当前身份挂到 request.state，未登录时为 None。"""
    request.state.identity = get_session(request.cookies.get(SESSION_COOKIE))
    return await call_next(request)


def current_identity(request: Request) -> Identity:
    identity: Identity | None = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(status_code=401, detail="未认证")
    return identity
