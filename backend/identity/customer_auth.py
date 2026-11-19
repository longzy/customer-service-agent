"""客户认证依赖：解析客户 cookie，未登录/过期映射为统一错误码。"""

import logging
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.domain.errors import ErrorCode
from backend.identity import customer_sessions
from backend.identity.customer_sessions import ResolvedCustomerSession
from backend.platform.db import get_read_session
from backend.platform.http import settings_of


async def current_customer_session(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_read_session, scope="function")],
) -> ResolvedCustomerSession:
    token = request.cookies.get(customer_sessions.CUSTOMER_COOKIE)
    if not token:
        raise ApiError(401, ErrorCode.SESSION_INVALID)
    try:
        resolved = await customer_sessions.resolve_customer_session(
            db, settings_of(request).m1_tenant_id, token
        )
    except customer_sessions.ExpiredSessionError:
        raise ApiError(401, ErrorCode.SESSION_EXPIRED) from None
    except customer_sessions.InvalidSessionError:
        raise ApiError(401, ErrorCode.SESSION_INVALID) from None
    now = customer_sessions.utc_now()
    if customer_sessions.needs_last_seen_refresh(resolved.last_seen_at, now):
        try:
            await customer_sessions.touch_customer_session_last_seen(resolved.session_id, now)
        except Exception:  # noqa: BLE001 - 活跃度记录失败不应让已认证的 GET 失败
            logging.getLogger(__name__).warning("刷新客户 last_seen_at 失败", exc_info=True)
    return resolved


CurrentCustomer = Annotated[ResolvedCustomerSession, Depends(current_customer_session)]
