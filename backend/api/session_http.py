"""认证路由共用：可信客户端 IP、UTC 文本、Cookie 与配置读取。"""

from datetime import UTC, datetime, timedelta

from fastapi import Request, Response

from backend.platform.settings import Settings


def client_ip(request: Request) -> str:
    """只信任直连 peer；不解析裸 X-Forwarded-For。"""
    return request.client.host if request.client is not None else "unknown"


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def settings_of(request: Request) -> Settings:
    active: Settings = request.app.state.settings
    return active


def set_session_cookie(
    response: Response,
    *,
    name: str,
    token: str,
    ttl: timedelta,
    active: Settings,
) -> None:
    response.set_cookie(
        name,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=active.secure_cookie,
        samesite="lax",
        path="/",
    )
