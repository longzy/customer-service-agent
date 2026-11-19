"""身份域 HTTP 入口：员工登录、当前会话恢复与登出。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.api.service_audit import audit_or_503, audit_security_event, trace_of
from backend.audit import EMPLOYEE_LOGIN, EMPLOYEE_LOGOUT, AuditRecord
from backend.domain.errors import ErrorCode
from backend.identity import employee_sessions
from backend.identity.cookies import set_session_cookie
from backend.identity.employee_auth import CurrentEmployee
from backend.identity.employee_sessions import Employee, ResolvedEmployeeSession
from backend.identity.schemas import (
    EmployeeLoginRequest,
    EmployeePublic,
    EmployeeSessionResponse,
)
from backend.platform.db import get_session
from backend.platform.http import client_ip, settings_of, utc_text
from backend.platform.schemas import ErrorEnvelope

router = APIRouter(prefix="/workspace", tags=["workspace"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
}

Db = Annotated[AsyncSession, Depends(get_session)]


def _employee_payload(employee: Employee) -> EmployeePublic:
    return EmployeePublic(
        id=employee.id,
        tenant_id=employee.tenant_id,
        username=employee.username,
        display_name=employee.display_name,
        role=employee.role,
    )


def _session_payload(session: ResolvedEmployeeSession) -> EmployeeSessionResponse:
    return EmployeeSessionResponse(
        employee=_employee_payload(session.employee),
        expires_at=utc_text(session.expires_at),
    )


@router.post(
    "/sessions",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        422: ERROR_RESPONSES[422],
        429: ERROR_RESPONSES[429],
    },
)
async def login(
    payload: EmployeeLoginRequest,
    request: Request,
    response: Response,
    db: Db,
) -> EmployeeSessionResponse:
    try:
        result = await employee_sessions.login_employee(
            db,
            settings_of(request).m1_tenant_id,
            payload.username,
            payload.password,
            client_ip(request),
        )
    except employee_sessions.RateLimitedError as error:
        await audit_security_event(
            request,
            429,
            ErrorCode.RATE_LIMITED,
            metadata={"username": payload.username},
        )
        raise ApiError(
            429,
            ErrorCode.RATE_LIMITED,
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from None
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
    if result is None:
        await audit_security_event(
            request,
            401,
            ErrorCode.AUTH_FAILED,
            metadata={"username": payload.username},
        )
        raise ApiError(401, ErrorCode.AUTH_FAILED)
    await audit_or_503(
        request,
        db,
        AuditRecord(
            tenant_id=result.employee.tenant_id,
            actor_type="employee",
            actor_id=result.employee.id,
            event_type=EMPLOYEE_LOGIN,
            entity_type="employee_session",
            entity_id=result.session_id,
            trace_id=trace_of(request),
            metadata={"username": result.employee.username},
        ),
    )
    set_session_cookie(
        response,
        name=employee_sessions.EMPLOYEE_COOKIE,
        token=result.token,
        ttl=employee_sessions.EMPLOYEE_SESSION_TTL,
        active=settings_of(request),
    )
    return EmployeeSessionResponse(
        employee=_employee_payload(result.employee),
        expires_at=utc_text(result.expires_at),
    )


@router.get("/session", responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403]})
async def current_session(session: CurrentEmployee) -> EmployeeSessionResponse:
    return _session_payload(session)


@router.delete("/sessions", status_code=204)
async def logout(request: Request, response: Response, db: Db) -> None:
    token = request.cookies.get(employee_sessions.EMPLOYEE_COOKIE)
    if token:
        try:
            resolved = await employee_sessions.resolve_employee_session(
                db, settings_of(request).m1_tenant_id, token
            )
        except (
            employee_sessions.ExpiredSessionError,
            employee_sessions.InvalidSessionError,
            employee_sessions.ForbiddenRoleError,
        ):
            resolved = None
        if resolved is not None:
            await audit_or_503(
                request,
                db,
                AuditRecord(
                    tenant_id=resolved.employee.tenant_id,
                    actor_type="employee",
                    actor_id=resolved.employee.id,
                    event_type=EMPLOYEE_LOGOUT,
                    entity_type="employee_session",
                    entity_id=resolved.session_id,
                    trace_id=trace_of(request),
                    metadata={"username": resolved.employee.username},
                ),
            )
        await employee_sessions.revoke_employee_session(db, token)
    response.delete_cookie(employee_sessions.EMPLOYEE_COOKIE, path="/")
