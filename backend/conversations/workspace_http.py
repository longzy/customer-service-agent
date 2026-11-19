"""会话域 HTTP 入口：工作台队列、领取、接管、回复、关闭与转回 AI。"""

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.api.service_audit import audit_or_503, trace_of
from backend.audit import (
    CONVERSATION_CLOSED,
    CONVERSATION_RETURNED_TO_AI,
    CONVERSATION_TAKEN_OVER,
    HANDOFF_CLAIMED,
    MESSAGE_REPLIED,
    AuditRecord,
)
from backend.conversations.customer_chat import MessageView
from backend.conversations.schemas import (
    AgentMessageRequest,
    MessagePageResponse,
    MessagePublic,
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
from backend.identity.employee_auth import CurrentEmployee
from backend.platform.db import get_session
from backend.platform.http import utc_text
from backend.platform.schemas import ErrorEnvelope

router = APIRouter(prefix="/workspace", tags=["workspace"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
}

Db = Annotated[AsyncSession, Depends(get_session)]


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
        failure_count=handoff.failure_count,
        last_error=handoff.last_error,
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
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    except ClaimConflictError:
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
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    except ClaimConflictError:
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
    return _state_change_payload(result)
