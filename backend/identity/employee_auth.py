"""员工认证依赖：解析工作台 cookie，未登录/过期/越权映射为统一错误码。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.api.service_audit import audit_security_event
from backend.domain.errors import ErrorCode
from backend.identity import employee_sessions
from backend.identity.employee_sessions import ResolvedEmployeeSession
from backend.platform.db import get_session
from backend.platform.http import settings_of


async def current_employee_session(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ResolvedEmployeeSession:
    token = request.cookies.get(employee_sessions.EMPLOYEE_COOKIE)
    if not token:
        raise ApiError(401, ErrorCode.SESSION_INVALID)
    try:
        return await employee_sessions.resolve_employee_session(
            db, settings_of(request).m1_tenant_id, token
        )
    except employee_sessions.ExpiredSessionError:
        raise ApiError(401, ErrorCode.SESSION_EXPIRED) from None
    except employee_sessions.ForbiddenRoleError as error:
        await audit_security_event(
            request,
            403,
            ErrorCode.FORBIDDEN,
            actor_type="employee",
            actor_id=error.employee_id or "anonymous",
            metadata={"username": error.username},
        )
        raise ApiError(403, ErrorCode.FORBIDDEN) from None
    except employee_sessions.InvalidSessionError:
        raise ApiError(401, ErrorCode.SESSION_INVALID) from None


CurrentEmployee = Annotated[ResolvedEmployeeSession, Depends(current_employee_session)]
