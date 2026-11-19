"""身份域 Cookie 写入：客户与员工 session 共用同一套安全属性。"""

from datetime import timedelta

from fastapi import Response

from backend.platform.settings import Settings


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
