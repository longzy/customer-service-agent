"""坐席工作台 API：员工登录、session 恢复、登出与会话归属门禁。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.customer_schemas import ErrorEnvelope
from backend.api.errors import ApiError
from backend.api.session_http import client_ip, set_session_cookie, settings_of, utc_text
from backend.api.workspace_schemas import (
    EmployeeLoginRequest,
    EmployeePublic,
    EmployeeSessionResponse,
    WorkspaceConversationResponse,
)
from backend.conversations.workspace_conversations import get_assigned_conversation
from backend.domain.errors import ErrorCode
from backend.identity import employee_sessions
from backend.identity.employee_sessions import Employee, ResolvedEmployeeSession
from backend.platform.db import get_session

router = APIRouter(prefix="/workspace", tags=["workspace"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
}


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
    except employee_sessions.ForbiddenRoleError:
        raise ApiError(403, ErrorCode.FORBIDDEN) from None
    except employee_sessions.InvalidSessionError:
        raise ApiError(401, ErrorCode.SESSION_INVALID) from None


CurrentEmployee = Annotated[ResolvedEmployeeSession, Depends(current_employee_session)]
Db = Annotated[AsyncSession, Depends(get_session)]


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
        raise ApiError(
            429,
            ErrorCode.RATE_LIMITED,
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from None
    except employee_sessions.ForbiddenRoleError:
        raise ApiError(403, ErrorCode.FORBIDDEN) from None
    if result is None:
        raise ApiError(401, ErrorCode.AUTH_FAILED)
    await db.commit()
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


@router.get(
    "/conversations/{conversation_id}",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
    },
)
async def read_conversation(
    conversation_id: str,
    session: CurrentEmployee,
    db: Db,
) -> WorkspaceConversationResponse:
    conversation = await get_assigned_conversation(
        db,
        session.employee.tenant_id,
        session.employee.id,
        conversation_id,
    )
    if conversation is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    return WorkspaceConversationResponse(
        id=conversation.id,
        status=conversation.status,  # type: ignore[arg-type]
    )


@router.delete("/sessions", status_code=204)
async def logout(request: Request, response: Response, db: Db) -> None:
    token = request.cookies.get(employee_sessions.EMPLOYEE_COOKIE)
    if token:
        await employee_sessions.logout_employee(db, token)
    response.delete_cookie(employee_sessions.EMPLOYEE_COOKIE, path="/")
