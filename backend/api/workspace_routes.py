"""坐席工作台 API：员工登录、session 恢复、登出与会话归属门禁。"""

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.customer_schemas import (
    ErrorEnvelope,
    MessagePageResponse,
    MessagePublic,
)
from backend.api.errors import ApiError
from backend.api.service_audit import audit_or_503, trace_of
from backend.api.session_http import client_ip, set_session_cookie, settings_of, utc_text
from backend.api.workspace_schemas import (
    AgentMessageRequest,
    EmployeeLoginRequest,
    EmployeePublic,
    EmployeeSessionResponse,
    WorkspaceAiTraceEvent,
    WorkspaceClaimResponse,
    WorkspaceContextMessage,
    WorkspaceConversationResponse,
    WorkspaceCustomerPublic,
    WorkspaceHandoffDetail,
    WorkspaceQueueItem,
    WorkspaceQueueResponse,
    WorkspaceTakeoverResponse,
)
from backend.audit import (
    CONVERSATION_CLOSED,
    CONVERSATION_RETURNED_TO_AI,
    CONVERSATION_TAKEN_OVER,
    EMPLOYEE_LOGIN,
    EMPLOYEE_LOGOUT,
    HANDOFF_CLAIMED,
    MESSAGE_REPLIED,
    AuditRecord,
)
from backend.conversations.customer_chat import MessageView
from backend.conversations.workspace_conversations import (
    ClaimConflictError,
    ConversationMessages,
    HandoffClosedError,
    HandoffDetail,
    WorkspaceConversationDetail,
    claim_handoff,
    get_assigned_conversation_detail,
    list_queued_handoffs,
    take_over_conversation,
    utc_now,
)
from backend.conversations.workspace_conversations import (
    read_conversation_messages as read_workspace_messages,
)
from backend.conversations.workspace_conversations import (
    reply_to_conversation as write_agent_reply,
)
from backend.conversations.workspace_lifecycle import (
    AgentStateChange,
    close_conversation_by_agent,
)
from backend.conversations.workspace_lifecycle import (
    ConversationClosedError as AgentConversationClosedError,
)
from backend.conversations.workspace_lifecycle import (
    return_conversation_to_ai as return_agent_conversation_to_ai,
)
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


def _handoff_payload(handoff: HandoffDetail) -> WorkspaceHandoffDetail:
    return WorkspaceHandoffDetail(
        id=handoff.id,
        status=handoff.status,
        reason=handoff.reason,
        summary=handoff.summary,
        pending_step=handoff.pending_step,
        order_count=handoff.order_count,
        messages=[WorkspaceContextMessage.model_validate(item) for item in handoff.messages],
        ai_trace=[WorkspaceAiTraceEvent.model_validate(item) for item in handoff.ai_trace],
    )


def _conversation_payload(
    conversation: WorkspaceConversationDetail,
) -> WorkspaceConversationResponse:
    return WorkspaceConversationResponse(
        id=conversation.id,
        status=conversation.status,  # type: ignore[arg-type]
        customer=WorkspaceCustomerPublic(
            username=conversation.customer.username,
            display_name=conversation.customer.display_name,
        ),
        handoff=(
            _handoff_payload(conversation.handoff) if conversation.handoff is not None else None
        ),
    )


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", None) or str(uuid4())


def _message_payload(message: MessageView) -> MessagePublic:
    return MessagePublic(
        id=message.id,
        author_type=message.author_type,  # type: ignore[arg-type]
        content=message.content,
        created_at=utc_text(message.created_at),
    )


def _messages_payload(result: ConversationMessages) -> MessagePageResponse:
    return MessagePageResponse(
        conversation_id=result.conversation_id,
        status=result.status,  # type: ignore[arg-type]
        after_id=result.after_id,
        messages=[_message_payload(message) for message in result.messages],
    )


def _state_change_payload(result: AgentStateChange) -> MessagePageResponse:
    return MessagePageResponse(
        conversation_id=result.conversation_id,
        status=result.status,  # type: ignore[arg-type]
        after_id=result.message.id,
        messages=[_message_payload(result.message)],
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


@router.get("/queue", responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403]})
async def read_queue(session: CurrentEmployee, db: Db) -> WorkspaceQueueResponse:
    items = await list_queued_handoffs(db, session.employee.tenant_id)
    return WorkspaceQueueResponse(
        items=[WorkspaceQueueItem.model_validate(item, from_attributes=True) for item in items]
    )


@router.post(
    "/queue/{handoff_id}/claim",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
    },
)
async def claim_queue_item(
    handoff_id: str,
    request: Request,
    session: CurrentEmployee,
    db: Db,
) -> WorkspaceClaimResponse:
    """条件领取；并发失败方得到 409，跨租户/不存在 404。"""
    try:
        claimed = await claim_handoff(
            db,
            session.employee.tenant_id,
            session.employee.id,
            handoff_id,
            trace_id=_trace_id(request),
        )
    except HandoffClosedError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    except ClaimConflictError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CLAIM_CONFLICT) from None
    if claimed is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    await audit_or_503(
        request,
        db,
        AuditRecord(
            tenant_id=session.employee.tenant_id,
            actor_type="employee",
            actor_id=session.employee.id,
            event_type=HANDOFF_CLAIMED,
            entity_type="handoff",
            entity_id=claimed.handoff_id,
            trace_id=trace_of(request),
            journey_id=claimed.journey_id,
            metadata={
                "conversation_id": claimed.conversation_id,
                "handoff_id": claimed.handoff_id,
                "to_status": claimed.status,
            },
        ),
    )
    await db.commit()
    return WorkspaceClaimResponse.model_validate(claimed, from_attributes=True)


@router.post(
    "/conversations/{conversation_id}/takeover",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
    },
)
async def take_over(
    conversation_id: str,
    request: Request,
    session: CurrentEmployee,
    db: Db,
) -> WorkspaceTakeoverResponse:
    """领取者接管；非本人/未领取/已接管 404，已关闭 409。"""
    try:
        taken = await take_over_conversation(
            db,
            session.employee.tenant_id,
            session.employee.id,
            conversation_id,
            trace_id=_trace_id(request),
        )
    except HandoffClosedError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    except ClaimConflictError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CLAIM_CONFLICT) from None
    if taken is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    await audit_or_503(
        request,
        db,
        AuditRecord(
            tenant_id=session.employee.tenant_id,
            actor_type="employee",
            actor_id=session.employee.id,
            event_type=CONVERSATION_TAKEN_OVER,
            entity_type="conversation",
            entity_id=taken.conversation_id,
            trace_id=trace_of(request),
            journey_id=taken.journey_id,
            metadata={"conversation_id": taken.conversation_id, "to_status": taken.status},
        ),
    )
    await db.commit()
    return WorkspaceTakeoverResponse.model_validate(taken, from_attributes=True)


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
    conversation = await get_assigned_conversation_detail(
        db,
        session.employee.tenant_id,
        session.employee.id,
        conversation_id,
    )
    if conversation is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    return _conversation_payload(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
    },
)
async def read_conversation_messages(
    conversation_id: str,
    session: CurrentEmployee,
    db: Db,
    after_id: int = Query(default=0, ge=0),
) -> MessagePageResponse:
    """归属坐席按 `after_id` 增量轮询；未领取/他人/跨租户 404，已关闭仍可读历史。"""
    result = await read_workspace_messages(
        db,
        session.employee.tenant_id,
        session.employee.id,
        conversation_id,
        after_id,
    )
    if result is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    await db.commit()
    return _messages_payload(result)


@router.post(
    "/conversations/{conversation_id}/messages",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
    },
)
async def reply_to_conversation(
    conversation_id: str,
    payload: AgentMessageRequest,
    request: Request,
    session: CurrentEmployee,
    db: Db,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=64),
) -> MessagePageResponse:
    """接管后回复；未接管/他人 404，已关闭 409，同幂等键重放返回原消息。"""
    try:
        result = await write_agent_reply(
            db,
            session.employee.tenant_id,
            session.employee.id,
            conversation_id,
            content=payload.content,
            idempotency_key=idempotency_key,
            trace_id=_trace_id(request),
            now=utc_now(),
        )
    except HandoffClosedError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    if result is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    if not result.replayed:
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.employee.tenant_id,
                actor_type="employee",
                actor_id=session.employee.id,
                event_type=MESSAGE_REPLIED,
                entity_type="message",
                entity_id=str(result.message.id),
                trace_id=trace_of(request),
                journey_id=result.journey_id,
                metadata={
                    "conversation_id": result.conversation_id,
                    "message_id": result.message.id,
                },
            ),
        )
    await db.commit()
    return MessagePageResponse(
        conversation_id=result.conversation_id,
        status=result.status,  # type: ignore[arg-type]
        after_id=result.message.id,
        messages=[_message_payload(result.message)],
    )


@router.post(
    "/conversations/{conversation_id}/close",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
    },
)
async def close_conversation(
    conversation_id: str,
    request: Request,
    session: CurrentEmployee,
    db: Db,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=64),
) -> MessagePageResponse:
    """坐席关闭已领取/人工中会话；已关闭 409，他人/跨租户/状态不可操作 404。"""
    try:
        result = await close_conversation_by_agent(
            db,
            session.employee.tenant_id,
            session.employee.id,
            conversation_id,
            idempotency_key=idempotency_key,
            trace_id=_trace_id(request),
            now=utc_now(),
        )
    except AgentConversationClosedError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    if result is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    if not result.replayed:
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.employee.tenant_id,
                actor_type="employee",
                actor_id=session.employee.id,
                event_type=CONVERSATION_CLOSED,
                entity_type="conversation",
                entity_id=result.conversation_id,
                trace_id=trace_of(request),
                journey_id=result.journey_id,
                metadata={"conversation_id": result.conversation_id, "to_status": result.status},
            ),
        )
    await db.commit()
    return _state_change_payload(result)


@router.post(
    "/conversations/{conversation_id}/return-to-ai",
    responses={
        401: ERROR_RESPONSES[401],
        403: ERROR_RESPONSES[403],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
    },
)
async def return_conversation_to_ai(
    conversation_id: str,
    request: Request,
    session: CurrentEmployee,
    db: Db,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=64),
) -> MessagePageResponse:
    """接管坐席把人工中会话转回 AI；非人工中/他人/跨租户 404，已关闭 409。"""
    try:
        result = await return_agent_conversation_to_ai(
            db,
            session.employee.tenant_id,
            session.employee.id,
            conversation_id,
            idempotency_key=idempotency_key,
            trace_id=_trace_id(request),
            now=utc_now(),
        )
    except AgentConversationClosedError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    if result is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    if not result.replayed:
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.employee.tenant_id,
                actor_type="employee",
                actor_id=session.employee.id,
                event_type=CONVERSATION_RETURNED_TO_AI,
                entity_type="conversation",
                entity_id=result.conversation_id,
                trace_id=trace_of(request),
                journey_id=result.journey_id,
                metadata={"conversation_id": result.conversation_id, "to_status": result.status},
            ),
        )
    await db.commit()
    return _state_change_payload(result)


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
        await db.commit()
    response.delete_cookie(employee_sessions.EMPLOYEE_COOKIE, path="/")
