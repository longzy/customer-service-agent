"""会话域 HTTP 入口：客户登录、会话读取、消息与关闭。"""

from datetime import datetime, timedelta
from typing import Annotated, Any, NoReturn
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
from backend.conversations.customer_cancellations import (
    CancellationSnapshot,
    CancellationStateConflict,
    CancellationTaskNotFound,
    can_confirm,
    confirm_cancellation,
    decline_cancellation,
    list_order_cancellations,
    refresh_cancellation,
    request_cancellation,
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
from backend.conversations.order_queries import (
    customer_order_summary,
    query_recent_orders,
)
from backend.conversations.schemas import (
    CancellationRequestCreate,
    CancellationSummary,
    CancellationTaskPublic,
    ConversationPublic,
    CustomerLoginRequest,
    CustomerMessageRequest,
    CustomerOrdersResponse,
    CustomerOrderSummary,
    CustomerPublic,
    CustomerSessionResponse,
    MessagePageResponse,
    MessagePayload,
    MessagePublic,
)
from backend.domain.cancellation import CancellationState, render_result
from backend.domain.errors import ErrorCode
from backend.identity import customer_sessions
from backend.identity.cookies import set_session_cookie
from backend.identity.customer_auth import CurrentCustomer
from backend.identity.customer_sessions import Customer
from backend.identity.rate_limit import consume_fixed_window
from backend.platform.db import get_read_session, get_session
from backend.platform.http import client_ip, settings_of, utc_text
from backend.platform.schemas import ErrorEnvelope
from backend.tools.gateway import GatewayError
from backend.workflows.cancel import CancellationTask, TaskConflict

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


def _cancellation_view(task: CancellationTask, now: datetime) -> CancellationTaskPublic:
    copy = render_result(task.state, task.reason_code)
    return CancellationTaskPublic(
        id=task.id,
        order_id=task.order_id,
        state=task.state.value,
        status_text=copy.state_text,
        reason_text=copy.reason_text,
        next_step=copy.next_step,
        reply=copy.reply,
        expires_at=utc_text(task.expires_at),
        confirmed_at=utc_text(task.confirmed_at) if task.confirmed_at else None,
        confirmation_source=task.confirmation_source,  # type: ignore[arg-type]
        can_confirm=task.state is CancellationState.AWAITING_CONFIRMATION and now < task.expires_at,
    )


def _cancellation_summary(snapshot: CancellationSnapshot, now: datetime) -> CancellationSummary:
    copy = render_result(snapshot.state, snapshot.reason_code)
    return CancellationSummary(
        state=snapshot.state.value,
        status_text=copy.state_text,
        next_step=copy.next_step,
        expires_at=utc_text(snapshot.expires_at),
        can_confirm=can_confirm(snapshot, now),
    )


def _raise_gateway_error(error: GatewayError) -> NoReturn:
    """取消网关失败按错误码归一；不把下游细节透给客户。"""
    if error.status_code == 404:
        raise ApiError(404, ErrorCode.NOT_FOUND_OR_UNAUTHORIZED)
    if error.status_code == 409:
        raise ApiError(409, ErrorCode.OMS_REJECTED)
    if error.status_code == 504:
        raise ApiError(504, ErrorCode.DEPENDENCY_TIMEOUT)
    if error.status_code == 503:
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE)
    if error.status_code == 502:
        raise ApiError(502, ErrorCode.INVALID_RESPONSE)
    raise ApiError(500, ErrorCode.INTERNAL_ERROR)


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


@router.get(
    "/orders",
    responses={
        401: ERROR_RESPONSES[401],
        422: ERROR_RESPONSES[422],
        503: {"model": ErrorEnvelope},
        504: {"model": ErrorEnvelope},
    },
)
async def list_orders(
    request: Request,
    session: CurrentCustomer,
    db: ReadDb,
    limit: int = Query(default=5, ge=1, le=5),
) -> CustomerOrdersResponse:
    """客户最近订单：本人同租户、白名单摘要；空列表不是错误。

    OMS 失败按依赖错误返回可重试状态，不影响聊天；访问审计复用 `audit_view`
    的 5 分钟去重，每次请求仍带 Trace。
    """
    trace_id = trace_of(request)
    outcome = await query_recent_orders(
        request.app.state.query_gateway,
        session.customer,
        trace_id,
        limit,
    )
    if outcome.status == "timeout":
        raise ApiError(504, ErrorCode.DEPENDENCY_TIMEOUT)
    if outcome.status == "error":
        raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE)
    conversation = await get_current_conversation(
        db, session.customer.tenant_id, session.customer.id
    )
    await audit_view(
        request,
        tenant_id=session.customer.tenant_id,
        actor_type="customer",
        actor_id=session.customer.id,
        # 列表没有单一订单实体；以客户作为列表访问的实体，避免把订单号写进审计。
        entity_type="order_list",
        entity_id=session.customer.id,
        journey_id=conversation.journey_id if conversation else None,
        source="customer",
    )
    now = customer_sessions.utc_now()
    summaries = [customer_order_summary(order) for order in outcome.orders]
    snapshots = await list_order_cancellations(
        db,
        session.customer,
        [str(summary["order_id"]) for summary in summaries],
        now=now,
    )
    orders = []
    for summary in summaries:
        snapshot = snapshots.get(str(summary["order_id"]))
        summary["cancellation"] = (
            _cancellation_summary(snapshot, now) if snapshot is not None else None
        )
        orders.append(CustomerOrderSummary.model_validate(summary))
    return CustomerOrdersResponse(orders=orders)


@router.post(
    "/cancellations",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
        422: ERROR_RESPONSES[422],
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
        504: {"model": ErrorEnvelope},
    },
)
async def create_cancellation(
    payload: CancellationRequestCreate,
    request: Request,
    session: CurrentCustomer,
    db: Db,
) -> CancellationTaskPublic:
    """发起取消：创建/复用任务并停在等待确认；资格拒绝不进入可提交状态。

    不调用 OMS 写接口；客户确认后才由 `CancellationWorkflow` 提交。
    """
    now = customer_sessions.utc_now()
    conversation = await get_current_conversation(
        db, session.customer.tenant_id, session.customer.id
    )
    try:
        task = await request_cancellation(
            db,
            request.app.state.cancel_gateway,
            session.customer,
            payload.order_id,
            trace_id=trace_of(request),
            now=now,
            confirm_timeout_minutes=settings_of(request).confirm_timeout_minutes,
            conversation_id=conversation.id if conversation else None,
        )
    except GatewayError as error:
        _raise_gateway_error(error)
    except (CancellationStateConflict, TaskConflict) as error:
        raise ApiError(409, ErrorCode.CANCELLATION_CONFLICT) from error
    return _cancellation_view(task, now)


@router.post(
    "/cancellations/{cancellation_id}/confirm",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
    },
)
async def confirm_customer_cancellation(
    cancellation_id: str,
    request: Request,
    session: CurrentCustomer,
    db: Db,
) -> CancellationTaskPublic:
    """客户确认：校验归属与状态后由 Workflow 只提交一次；过期视为未提交。"""
    now = customer_sessions.utc_now()
    try:
        task = await confirm_cancellation(
            db,
            request.app.state.cancel_gateway,
            session.customer,
            cancellation_id,
            now=now,
            confirm_timeout_minutes=settings_of(request).confirm_timeout_minutes,
        )
    except CancellationTaskNotFound as error:
        raise ApiError(404, ErrorCode.NOT_FOUND_OR_UNAUTHORIZED) from error
    except CancellationStateConflict as error:
        raise ApiError(409, ErrorCode.CANCELLATION_CONFLICT) from error
    return _cancellation_view(task, now)


@router.post(
    "/cancellations/{cancellation_id}/decline",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
    },
)
async def decline_customer_cancellation(
    cancellation_id: str,
    request: Request,
    session: CurrentCustomer,
    db: Db,
) -> CancellationTaskPublic:
    """客户拒绝：任务结束且不写 OMS；重复拒绝幂等返回。"""
    now = customer_sessions.utc_now()
    try:
        task = await decline_cancellation(
            db,
            request.app.state.cancel_gateway,
            session.customer,
            cancellation_id,
            now=now,
            confirm_timeout_minutes=settings_of(request).confirm_timeout_minutes,
        )
    except CancellationTaskNotFound as error:
        raise ApiError(404, ErrorCode.NOT_FOUND_OR_UNAUTHORIZED) from error
    except CancellationStateConflict as error:
        raise ApiError(409, ErrorCode.CANCELLATION_CONFLICT) from error
    return _cancellation_view(task, now)


@router.post(
    "/cancellations/{cancellation_id}/refresh",
    responses={
        401: ERROR_RESPONSES[401],
        404: ERROR_RESPONSES[404],
        409: ERROR_RESPONSES[409],
    },
)
async def refresh_customer_cancellation(
    cancellation_id: str,
    request: Request,
    session: CurrentCustomer,
    db: Db,
) -> CancellationTaskPublic:
    """结果刷新：惰性过期；已受理可按 OMS 结果推进到已取消/被拒绝。"""
    now = customer_sessions.utc_now()
    try:
        task = await refresh_cancellation(
            db,
            request.app.state.cancel_gateway,
            session.customer,
            cancellation_id,
            now=now,
            confirm_timeout_minutes=settings_of(request).confirm_timeout_minutes,
        )
    except CancellationTaskNotFound as error:
        raise ApiError(404, ErrorCode.NOT_FOUND_OR_UNAUTHORIZED) from error
    except CancellationStateConflict as error:
        raise ApiError(409, ErrorCode.CANCELLATION_CONFLICT) from error
    return _cancellation_view(task, now)


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
