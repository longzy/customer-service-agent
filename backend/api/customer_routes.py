"""客户 API：登录、当前会话恢复、按所有权读取会话与登出。"""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.conversations.customer_conversations import (
    CustomerConversation,
    get_customer_conversation,
    get_or_create_open_conversation,
)
from backend.domain.errors import ErrorCode
from backend.identity import customer_sessions
from backend.identity.customer_sessions import Customer, ResolvedCustomerSession
from backend.platform.db import get_session
from backend.platform.settings import Settings

router = APIRouter(prefix="/customer", tags=["customer"])


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


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _payload(
    customer: Customer, conversation: CustomerConversation, expires_at: datetime
) -> dict[str, Any]:
    return {
        "customer": {
            "id": customer.id,
            "tenant_id": customer.tenant_id,
            "username": customer.username,
            "display_name": customer.display_name,
        },
        "conversation": {
            "id": conversation.id,
            "status": conversation.status,
            "after_id": conversation.after_id,
        },
        "expires_at": _utc_text(expires_at),
    }


def _client_ip(request: Request) -> str:
    """只信任直连 peer；不解析裸 X-Forwarded-For。"""
    return request.client.host if request.client is not None else "unknown"


def _set_cookie(response: Response, token: str, active: Settings) -> None:
    response.set_cookie(
        customer_sessions.CUSTOMER_COOKIE,
        token,
        max_age=int(customer_sessions.CUSTOMER_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=active.secure_cookie,
        samesite="lax",
        path="/",
    )


def settings_of(request: Request) -> Settings:
    active: Settings = request.app.state.settings
    return active


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


@router.post("/sessions")
async def login(
    payload: CustomerLoginRequest,
    request: Request,
    response: Response,
    db: Db,
) -> dict[str, Any]:
    try:
        result = await customer_sessions.login_customer(
            db,
            settings_of(request).m1_tenant_id,
            payload.username,
            payload.password,
            _client_ip(request),
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
    _set_cookie(response, result.token, settings_of(request))
    return _payload(result.customer, conversation, result.expires_at)


@router.get("/session")
async def current_session(session: CurrentSession, db: Db) -> dict[str, Any]:
    conversation = await get_or_create_open_conversation(
        db,
        session.customer.tenant_id,
        session.customer.id,
        customer_sessions.utc_now(),
    )
    await db.commit()
    return _payload(session.customer, conversation, session.expires_at)


@router.get("/conversations/{conversation_id}")
async def read_conversation(
    conversation_id: str,
    session: CurrentSession,
    db: Db,
) -> dict[str, Any]:
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
