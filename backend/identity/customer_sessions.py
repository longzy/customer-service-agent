"""客户认证、session 与未关闭会话恢复（不依赖 FastAPI）。

- 密码：scrypt；账号不存在时也走一次 dummy 校验，统一 401。
- session：24h 绝对过期；登录轮换（撤销该客户全部旧 session）；只存 token 哈希。
- 会话：一个客户同时只有一个未关闭会话；AI_ACTIVE 空闲 24h 在登录/读状态时惰性关闭。
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.passwords import verify_dummy_password, verify_password
from backend.platform.models import (
    ServiceConversation,
    ServiceCustomer,
    ServiceCustomerSession,
    ServiceRateLimitBucket,
)

CUSTOMER_SESSION_TTL = timedelta(hours=24)
CONVERSATION_IDLE_TIMEOUT = timedelta(hours=24)
LOGIN_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)
CUSTOMER_COOKIE = "csid"
STATUS_AI_ACTIVE = "AI_ACTIVE"
STATUS_CLOSED = "CLOSED"


class InvalidSessionError(Exception):
    """session 不存在、已撤销或账号不可用。"""


class ExpiredSessionError(Exception):
    """session 已过期；与 InvalidSession 分开，便于返回不同错误码。"""


class RateLimitedError(Exception):
    """登录尝试超过窗口上限。"""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate limited")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class Customer:
    id: str
    tenant_id: str
    username: str
    display_name: str


@dataclass(frozen=True)
class CustomerConversation:
    id: str
    status: str
    after_id: int


@dataclass(frozen=True)
class CustomerLogin:
    token: str
    customer: Customer
    conversation: CustomerConversation
    expires_at: datetime


@dataclass(frozen=True)
class ResolvedCustomerSession:
    customer: Customer
    conversation: CustomerConversation
    expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    """token 只以 SHA-256 入库；256-bit 随机量无需再加盐。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _check_login_rate_limit(db: AsyncSession, username: str, ip: str) -> None:
    """固定窗口 5/15min；先写桶再校验业务，超限直接 429。"""
    now = utc_now()
    window_seconds = int(LOGIN_WINDOW.total_seconds())
    # 按整数秒对齐窗口，避免浮点误差把同一窗口拆成多个桶。
    epoch = int(now.timestamp())
    window_start = datetime.fromtimestamp(epoch - epoch % window_seconds, UTC)
    key = f"customer_login:{username.strip().lower()}:{ip}"
    statement = (
        insert(ServiceRateLimitBucket)
        .values(bucket_key=key, window_start=window_start, count=1)
        .on_conflict_do_update(
            index_elements=[
                ServiceRateLimitBucket.bucket_key,
                ServiceRateLimitBucket.window_start,
            ],
            set_={"count": ServiceRateLimitBucket.count + 1},
        )
        .returning(ServiceRateLimitBucket.count)
    )
    count = (await db.execute(statement)).scalar_one()
    await db.commit()
    if count > LOGIN_LIMIT:
        retry_after = int((window_start + LOGIN_WINDOW - now).total_seconds())
        raise RateLimitedError(max(retry_after, 1))


async def _lookup_customer(
    db: AsyncSession, tenant_id: str, username: str
) -> ServiceCustomer | None:
    statement = select(ServiceCustomer).where(
        ServiceCustomer.tenant_id == tenant_id,
        ServiceCustomer.username == username.strip(),
        ServiceCustomer.active.is_(True),
    )
    return (await db.execute(statement)).scalar_one_or_none()


def _customer(row: ServiceCustomer) -> Customer:
    return Customer(
        id=row.id,
        tenant_id=row.tenant_id,
        username=row.username,
        display_name=row.display_name,
    )


def _conversation(row: ServiceConversation) -> CustomerConversation:
    # service_messages 在 F-02 落地；本切片还没有消息，after_id 固定 0。
    return CustomerConversation(id=row.id, status=row.status, after_id=0)


async def _open_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str
) -> ServiceConversation | None:
    statement = (
        select(ServiceConversation)
        .where(
            ServiceConversation.tenant_id == tenant_id,
            ServiceConversation.customer_id == customer_id,
            ServiceConversation.status != STATUS_CLOSED,
        )
        .order_by(ServiceConversation.created_at.desc())
        .limit(1)
    )
    return (await db.execute(statement)).scalar_one_or_none()


async def _get_or_create_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str, now: datetime
) -> ServiceConversation:
    existing = await _open_conversation(db, tenant_id, customer_id)
    if existing is not None:
        stale = (
            existing.status == STATUS_AI_ACTIVE
            and existing.last_activity_at + CONVERSATION_IDLE_TIMEOUT <= now
        )
        if not stale:
            return existing
        # 惰性关闭：AI 空闲 24h；不引入后台 worker。
        existing.status = STATUS_CLOSED
        existing.closed_at = now
        existing.updated_at = now
        await db.flush()
    created = ServiceConversation(
        id=str(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        status=STATUS_AI_ACTIVE,
        journey_id=str(uuid4()),
        created_at=now,
        updated_at=now,
        last_activity_at=now,
    )
    db.add(created)
    await db.flush()
    return created


async def login_customer(
    db: AsyncSession,
    tenant_id: str,
    username: str,
    password: str,
    client_ip: str,
) -> CustomerLogin | None:
    """凭据正确返回登录结果；失败返回 None（调用方统一 401）。"""
    await _check_login_rate_limit(db, username, client_ip)
    row = await _lookup_customer(db, tenant_id, username)
    if row is None:
        verify_dummy_password(password)
        return None
    if not verify_password(password, row.password_hash):
        return None

    now = utc_now()
    token = secrets.token_urlsafe(32)
    # 登录轮换：撤销该客户全部旧 session，旧 cookie 立即 401。
    await db.execute(
        update(ServiceCustomerSession)
        .where(
            ServiceCustomerSession.customer_id == row.id,
            ServiceCustomerSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    expires_at = now + CUSTOMER_SESSION_TTL
    db.add(
        ServiceCustomerSession(
            id=str(uuid4()),
            customer_id=row.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=expires_at,
        )
    )
    conversation = await _get_or_create_conversation(db, tenant_id, row.id, now)
    await db.commit()
    return CustomerLogin(
        token=token,
        customer=_customer(row),
        conversation=_conversation(conversation),
        expires_at=expires_at,
    )


async def resolve_customer_session(
    db: AsyncSession, tenant_id: str, token: str
) -> ResolvedCustomerSession:
    """按 cookie token 恢复客户与未关闭会话；失效抛两类异常。"""
    now = utc_now()
    statement = select(ServiceCustomerSession).where(
        ServiceCustomerSession.token_hash == hash_token(token)
    )
    row = (await db.execute(statement)).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise InvalidSessionError
    if row.expires_at <= now:
        raise ExpiredSessionError
    customer = await db.get(ServiceCustomer, row.customer_id)
    if customer is None or not customer.active or customer.tenant_id != tenant_id:
        raise InvalidSessionError

    row.last_seen_at = now
    conversation = await _get_or_create_conversation(db, tenant_id, customer.id, now)
    await db.commit()
    return ResolvedCustomerSession(
        customer=_customer(customer),
        conversation=_conversation(conversation),
        expires_at=row.expires_at,
    )


async def logout_customer(db: AsyncSession, token: str) -> None:
    """撤销当前 session；无 cookie 或已失效也返回成功（幂等登出）。"""
    now = utc_now()
    await db.execute(
        update(ServiceCustomerSession)
        .where(
            ServiceCustomerSession.token_hash == hash_token(token),
            ServiceCustomerSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.commit()


async def get_customer_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str, conversation_id: str
) -> CustomerConversation | None:
    """按所有权读取会话；他人/跨租户/不存在都返回 None，由调用方统一 404。"""
    statement = select(ServiceConversation).where(
        ServiceConversation.id == conversation_id,
        ServiceConversation.tenant_id == tenant_id,
        ServiceConversation.customer_id == customer_id,
    )
    row = (await db.execute(statement)).scalar_one_or_none()
    return _conversation(row) if row is not None else None
