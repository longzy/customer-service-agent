"""会话域 HTTP 入口：客户登录、会话读取、消息与关闭。"""

from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.api.service_audit import audit_or_503, audit_security_event, audit_view, trace_of
from backend.audit import (
    AI_REPLIED,
    CONVERSATION_CLOSED,
    CUSTOMER_LOGIN,
    CUSTOMER_LOGOUT,
    HANDOFF_CREATED,
    MESSAGE_SENT,
    ORDER_QUERIED,
    AuditRecord,
)
from backend.conversations.customer_chat import (
    ChatResult,
    ConversationClosedError,
    MessageView,
    read_customer_messages,
    send_customer_message,
)
from backend.conversations.customer_close import close_customer_conversation
from backend.conversations.customer_conversations import (
    CustomerConversation,
    get_current_conversation,
    get_customer_conversation,
    get_or_create_open_conversation,
    get_sendable_conversation,
)
from backend.conversations.schemas import (
    ConversationPublic,
    CustomerLoginRequest,
    CustomerMessageRequest,
    CustomerPublic,
    CustomerSessionResponse,
    MessagePageResponse,
    MessagePayload,
    MessagePublic,
)
from backend.domain.errors import ErrorCode
from backend.identity import customer_sessions
from backend.identity.cookies import set_session_cookie
from backend.identity.customer_auth import CurrentCustomer
from backend.identity.customer_sessions import Customer
from backend.identity.rate_limit import consume_fixed_window
from backend.platform.db import get_read_session, get_session
from backend.platform.http import client_ip, settings_of, utc_text
from backend.platform.schemas import ErrorEnvelope

router = APIRouter(prefix="/customer", tags=["customer"])

# plan 5.1：客户消息按 session 限速 30/min；限速先于消息写入
MESSAGE_LIMIT = 30
MESSAGE_WINDOW = timedelta(minutes=1)

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
}

Db = Annotated[AsyncSession, Depends(get_session, scope="function")]
ReadDb = Annotated[AsyncSession, Depends(get_read_session, scope="function")]


def _payload(
    customer: Customer, conversation: CustomerConversation, expires_at: datetime
) -> CustomerSessionResponse:
    return CustomerSessionResponse(
        customer=CustomerPublic(
            id=customer.id,
            tenant_id=customer.tenant_id,
            username=customer.username,
            display_name=customer.display_name,
        ),
        conversation=ConversationPublic(
            id=conversation.id,
            status=conversation.status,  # type: ignore[arg-type]
            after_id=conversation.after_id,
        ),
        expires_at=utc_text(expires_at),
    )


def _message_json(message: MessageView) -> MessagePublic:
    return MessagePublic(
        id=message.id,
        author_type=message.author_type,  # type: ignore[arg-type]
        content=message.content,
        created_at=utc_text(message.created_at),
        payload=MessagePayload.from_stored(message.payload),
    )


def _chat_payload(result: ChatResult) -> MessagePageResponse:
    return MessagePageResponse(
        conversation_id=result.conversation_id,
        status=result.status,  # type: ignore[arg-type]
        after_id=result.after_id,
        messages=[_message_json(message) for message in result.messages],
    )


@router.post(
    "/sessions",
    responses={401: ERROR_RESPONSES[401], 422: ERROR_RESPONSES[422], 429: ERROR_RESPONSES[429]},
)
async def login(
    payload: CustomerLoginRequest,
    request: Request,
    response: Response,
    db: Db,
) -> CustomerSessionResponse:
    try:
        result = await customer_sessions.login_customer(
            db,
            settings_of(request).m1_tenant_id,
            payload.username,
            payload.password,
            client_ip(request),
        )
    except customer_sessions.RateLimitedError as error:
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
    if result is None:
        await audit_security_event(
            request,
            401,
            ErrorCode.AUTH_FAILED,
            metadata={"username": payload.username},
        )
        raise ApiError(401, ErrorCode.AUTH_FAILED)
    conversation = await get_or_create_open_conversation(
        db,
        result.customer.tenant_id,
        result.customer.id,
        customer_sessions.utc_now(),
    )
    await audit_or_503(
        request,
        db,
        AuditRecord(
            tenant_id=result.customer.tenant_id,
            actor_type="customer",
            actor_id=result.customer.id,
            event_type=CUSTOMER_LOGIN,
            entity_type="customer_session",
            entity_id=result.session_id,
            trace_id=trace_of(request),
            journey_id=conversation.journey_id,
            metadata={"conversation_id": conversation.id, "username": result.customer.username},
        ),
    )
    set_session_cookie(
        response,
        name=customer_sessions.CUSTOMER_COOKIE,
        token=result.token,
        ttl=customer_sessions.CUSTOMER_SESSION_TTL,
        active=settings_of(request),
    )
    return _payload(result.customer, conversation, result.expires_at)


@router.get("/session", responses={401: ERROR_RESPONSES[401]})
async def current_session(session: CurrentCustomer, db: Db) -> CustomerSessionResponse:
    conversation = await get_or_create_open_conversation(
        db,
        session.customer.tenant_id,
        session.customer.id,
        customer_sessions.utc_now(),
    )
    return _payload(session.customer, conversation, session.expires_at)


@router.get(
    "/conversations/{conversation_id}",
    responses={401: ERROR_RESPONSES[401], 404: ERROR_RESPONSES[404]},
)
async def read_conversation(
    conversation_id: str,
    request: Request,
    session: CurrentCustomer,
    db: ReadDb,
) -> CustomerSessionResponse:
    conversation = await get_customer_conversation(
        db,
        session.customer.tenant_id,
        session.customer.id,
        conversation_id,
    )
    # last_seen_at 由认证依赖按 5 分钟节流刷新；本路由不再写业务事务。
    if conversation is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    await audit_view(
        request,
        tenant_id=session.customer.tenant_id,
        actor_type="customer",
        actor_id=session.customer.id,
        entity_type="conversation",
        entity_id=conversation.id,
        journey_id=conversation.journey_id,
        source="customer",
    )
    return _payload(session.customer, conversation, session.expires_at)


@router.post(
    "/messages",
    responses={
        401: ERROR_RESPONSES[401],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
        429: ERROR_RESPONSES[429],
    },
)
async def send_message(
    payload: CustomerMessageRequest,
    request: Request,
    session: CurrentCustomer,
    db: Db,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=64),
) -> MessagePageResponse:
    now = customer_sessions.utc_now()
    try:
        await consume_fixed_window(
            bucket_key=f"msg:{session.session_id}",
            limit=MESSAGE_LIMIT,
            window=MESSAGE_WINDOW,
            now=now,
        )
    except customer_sessions.RateLimitedError as error:
        await audit_security_event(
            request,
            429,
            ErrorCode.RATE_LIMITED,
            actor_type="customer",
            actor_id=session.customer.id,
            metadata={"username": session.customer.username},
        )
        raise ApiError(
            429,
            ErrorCode.RATE_LIMITED,
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from None
    conversation = await get_sendable_conversation(
        db, session.customer.tenant_id, session.customer.id, now
    )
    if conversation is None:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED)
    trace_id = trace_of(request)
    try:
        result = await send_customer_message(
            db,
            conversation,
            customer_id=session.customer.id,
            content=payload.content,
            idempotency_key=idempotency_key,
            model=request.app.state.model_client,
            timeout_seconds=settings_of(request).customer_model_timeout_seconds,
            trace_id=trace_id,
            now=now,
            customer=session.customer,
            order_gateway=request.app.state.query_gateway,
        )
    except ConversationClosedError:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    if not result.replayed and result.customer_message_id is not None:
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.customer.tenant_id,
                actor_type="customer",
                actor_id=session.customer.id,
                event_type=MESSAGE_SENT,
                entity_type="message",
                entity_id=str(result.customer_message_id),
                trace_id=trace_id,
                journey_id=conversation.journey_id,
                metadata={
                    "conversation_id": conversation.id,
                    "message_id": result.customer_message_id,
                },
            ),
        )
    if result.order_query is not None:
        # AC-57：每次真实订单查询一条审计；重放不带 query，不重复写。
        order_query = result.order_query
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.customer.tenant_id,
                actor_type="customer",
                actor_id=session.customer.id,
                event_type=ORDER_QUERIED,
                # 单笔查询的实体是订单；列表查询的实体是会话，避免把会话 id 挂到 order 上。
                entity_type="order" if order_query.order_id else "conversation",
                entity_id=(order_query.order_id or conversation.id)[:64],
                trace_id=trace_id,
                journey_id=conversation.journey_id,
                metadata={
                    "conversation_id": conversation.id,
                    "order_id": order_query.order_id,
                    "order_count": order_query.order_count,
                    "result": order_query.result,
                    "tool": order_query.tool,
                    "error_code": order_query.error_code,
                },
            ),
        )
    if result.handoff_id is not None:
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.customer.tenant_id,
                actor_type="customer",
                actor_id=session.customer.id,
                event_type=HANDOFF_CREATED,
                entity_type="handoff",
                entity_id=result.handoff_id,
                trace_id=trace_id,
                journey_id=conversation.journey_id,
                metadata={
                    "conversation_id": conversation.id,
                    "handoff_id": result.handoff_id,
                    "trigger": "customer_message",
                },
            ),
        )
    if result.ai_message_id is not None:
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.customer.tenant_id,
                actor_type="system",
                actor_id="system",
                event_type=AI_REPLIED,
                entity_type="message",
                entity_id=str(result.ai_message_id),
                trace_id=trace_id,
                journey_id=conversation.journey_id,
                metadata={
                    "conversation_id": conversation.id,
                    "message_id": result.ai_message_id,
                },
            ),
        )
    return _chat_payload(result)


@router.get("/messages", responses={401: ERROR_RESPONSES[401], 409: ERROR_RESPONSES[409]})
async def read_messages(
    session: CurrentCustomer,
    db: ReadDb,
    after_id: int = Query(default=0, ge=0),
) -> MessagePageResponse:
    conversation = await get_current_conversation(
        db, session.customer.tenant_id, session.customer.id
    )
    if conversation is None:
        # 已关闭会话仍可读历史；读接口不返回 409。
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED)
    result = await read_customer_messages(db, conversation, after_id)
    return _chat_payload(result)


@router.post(
    "/session/close",
    responses={
        401: ERROR_RESPONSES[401],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
    },
)
async def close_session(
    request: Request,
    session: CurrentCustomer,
    db: Db,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=64),
) -> MessagePageResponse:
    """客户关闭任意未关闭会话；交接单同事务终态化，同键重放幂等。"""
    now = customer_sessions.utc_now()
    conversation = await get_current_conversation(
        db, session.customer.tenant_id, session.customer.id
    )
    if conversation is None:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED)
    trace_id = getattr(request.state, "trace_id", None) or str(uuid4())
    # 条件 UPDATE 会同步 ORM 对象状态；审计的 from_status 必须在关闭前取快照。
    from_status = conversation.status
    try:
        result = await close_customer_conversation(
            db,
            conversation,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            now=now,
        )
    except ConversationClosedError:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    if not result.replayed:
        await audit_or_503(
            request,
            db,
            AuditRecord(
                tenant_id=session.customer.tenant_id,
                actor_type="customer",
                actor_id=session.customer.id,
                event_type=CONVERSATION_CLOSED,
                entity_type="conversation",
                entity_id=conversation.id,
                trace_id=trace_id,
                journey_id=conversation.journey_id,
                metadata={
                    "conversation_id": conversation.id,
                    "from_status": from_status,
                    "to_status": "CLOSED",
                },
            ),
        )
    return _chat_payload(result)


@router.delete("/sessions", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: Db,
) -> None:
    token = request.cookies.get(customer_sessions.CUSTOMER_COOKIE)
    if token:
        try:
            resolved = await customer_sessions.resolve_customer_session(
                db, settings_of(request).m1_tenant_id, token
            )
        except (customer_sessions.ExpiredSessionError, customer_sessions.InvalidSessionError):
            resolved = None
        if resolved is not None:
            await audit_or_503(
                request,
                db,
                AuditRecord(
                    tenant_id=resolved.customer.tenant_id,
                    actor_type="customer",
                    actor_id=resolved.customer.id,
                    event_type=CUSTOMER_LOGOUT,
                    entity_type="customer_session",
                    entity_id=resolved.session_id,
                    trace_id=trace_of(request),
                    metadata={"username": resolved.customer.username},
                ),
            )
        await customer_sessions.revoke_customer_session(db, token)
    response.delete_cookie(customer_sessions.CUSTOMER_COOKIE, path="/")
