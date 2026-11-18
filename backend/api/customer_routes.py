"""客户 API：登录、当前会话恢复、按所有权读取会话与登出。"""

from datetime import datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.customer_schemas import (
    ConversationPublic,
    CustomerPublic,
    CustomerSessionResponse,
    ErrorEnvelope,
    MessagePageResponse,
    MessagePublic,
)
from backend.api.errors import ApiError
from backend.api.session_http import client_ip, set_session_cookie, settings_of, utc_text
from backend.conversations.customer_chat import (
    ChatResult,
    ConversationClosedError,
    MessageView,
    read_customer_messages,
    send_customer_message,
)
from backend.conversations.customer_close import (
    ConversationCloseConflictError,
    close_customer_conversation,
)
from backend.conversations.customer_conversations import (
    CustomerConversation,
    get_customer_conversation,
    get_latest_conversation,
    get_open_conversation,
    get_or_create_open_conversation,
    get_sendable_conversation,
)
from backend.domain.errors import ErrorCode
from backend.identity import customer_sessions
from backend.identity.customer_sessions import Customer, ResolvedCustomerSession
from backend.platform.db import get_session

router = APIRouter(prefix="/customer", tags=["customer"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    429: {"model": ErrorEnvelope},
}


class CustomerMessageRequest(BaseModel):
    """客户消息；身份与会话只能来自服务端 session。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content 不能为空")
        return value


class CustomerLoginRequest(BaseModel):
    """只接受用户名/密码；租户与客户 id 只能来自服务端配置与 session。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username 不能为空")
        return value


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
    )


def _chat_payload(result: ChatResult) -> MessagePageResponse:
    return MessagePageResponse(
        conversation_id=result.conversation_id,
        status=result.status,  # type: ignore[arg-type]
        after_id=result.after_id,
        messages=[_message_json(message) for message in result.messages],
    )


async def current_customer_session(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ResolvedCustomerSession:
    token = request.cookies.get(customer_sessions.CUSTOMER_COOKIE)
    if not token:
        raise ApiError(401, ErrorCode.SESSION_INVALID)
    try:
        return await customer_sessions.resolve_customer_session(
            db, settings_of(request).m1_tenant_id, token
        )
    except customer_sessions.ExpiredSessionError:
        raise ApiError(401, ErrorCode.SESSION_EXPIRED) from None
    except customer_sessions.InvalidSessionError:
        raise ApiError(401, ErrorCode.SESSION_INVALID) from None


CurrentSession = Annotated[ResolvedCustomerSession, Depends(current_customer_session)]
Db = Annotated[AsyncSession, Depends(get_session)]


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
        raise ApiError(
            429,
            ErrorCode.RATE_LIMITED,
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from None
    if result is None:
        raise ApiError(401, ErrorCode.AUTH_FAILED)
    conversation = await get_or_create_open_conversation(
        db,
        result.customer.tenant_id,
        result.customer.id,
        customer_sessions.utc_now(),
    )
    await db.commit()
    set_session_cookie(
        response,
        name=customer_sessions.CUSTOMER_COOKIE,
        token=result.token,
        ttl=customer_sessions.CUSTOMER_SESSION_TTL,
        active=settings_of(request),
    )
    return _payload(result.customer, conversation, result.expires_at)


@router.get("/session", responses={401: ERROR_RESPONSES[401]})
async def current_session(session: CurrentSession, db: Db) -> CustomerSessionResponse:
    conversation = await get_or_create_open_conversation(
        db,
        session.customer.tenant_id,
        session.customer.id,
        customer_sessions.utc_now(),
    )
    await db.commit()
    return _payload(session.customer, conversation, session.expires_at)


@router.get(
    "/conversations/{conversation_id}",
    responses={401: ERROR_RESPONSES[401], 404: ERROR_RESPONSES[404]},
)
async def read_conversation(
    conversation_id: str,
    session: CurrentSession,
    db: Db,
) -> CustomerSessionResponse:
    conversation = await get_customer_conversation(
        db,
        session.customer.tenant_id,
        session.customer.id,
        conversation_id,
    )
    # 读取也会刷新 last_seen_at；保持 GET 幂等但落库。
    await db.commit()
    if conversation is None:
        raise ApiError(404, ErrorCode.NOT_FOUND)
    return _payload(session.customer, conversation, session.expires_at)


@router.post(
    "/messages",
    responses={401: ERROR_RESPONSES[401], 409: ERROR_RESPONSES[409], 422: ERROR_RESPONSES[422]},
)
async def send_message(
    payload: CustomerMessageRequest,
    request: Request,
    session: CurrentSession,
    db: Db,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=64),
) -> MessagePageResponse:
    now = customer_sessions.utc_now()
    conversation = await get_sendable_conversation(
        db, session.customer.tenant_id, session.customer.id, now
    )
    if conversation is None:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED)
    trace_id = getattr(request.state, "trace_id", None) or str(uuid4())
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
        )
    except ConversationClosedError:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    await db.commit()
    return _chat_payload(result)


@router.get("/messages", responses={401: ERROR_RESPONSES[401], 409: ERROR_RESPONSES[409]})
async def read_messages(
    session: CurrentSession,
    db: Db,
    after_id: int = Query(default=0, ge=0),
) -> MessagePageResponse:
    conversation = await get_open_conversation(db, session.customer.tenant_id, session.customer.id)
    if conversation is None:
        # 已关闭会话仍可读历史；读接口不返回 409。
        conversation = await get_latest_conversation(
            db, session.customer.tenant_id, session.customer.id
        )
    if conversation is None:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED)
    result = await read_customer_messages(db, conversation, after_id)
    await db.commit()
    return _chat_payload(result)


@router.post(
    "/session/close",
    responses={401: ERROR_RESPONSES[401], 409: ERROR_RESPONSES[409]},
)
async def close_session(
    request: Request,
    session: CurrentSession,
    db: Db,
) -> MessagePageResponse:
    """客户关闭任意未关闭会话；交接单同事务终态化，重复关闭幂等。"""
    now = customer_sessions.utc_now()
    conversation = await get_open_conversation(db, session.customer.tenant_id, session.customer.id)
    if conversation is None:
        # 没有未关闭会话时取最近一条：已关闭则返回 CLOSED 的空增量页（幂等）。
        conversation = await get_latest_conversation(
            db, session.customer.tenant_id, session.customer.id
        )
    if conversation is None:
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED)
    trace_id = getattr(request.state, "trace_id", None) or str(uuid4())
    try:
        result = await close_customer_conversation(
            db,
            conversation,
            trace_id=trace_id,
            now=now,
        )
    except ConversationCloseConflictError:
        await db.rollback()
        raise ApiError(409, ErrorCode.CONVERSATION_CLOSED) from None
    await db.commit()
    return _chat_payload(result)


@router.delete("/sessions", status_code=204)
async def logout(
    request: Request,
    response: Response,
    db: Db,
) -> None:
    token = request.cookies.get(customer_sessions.CUSTOMER_COOKIE)
    if token:
        await customer_sessions.logout_customer(db, token)
    response.delete_cookie(customer_sessions.CUSTOMER_COOKIE, path="/")
