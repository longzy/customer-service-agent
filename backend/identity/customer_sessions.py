"""客户认证与 session（不依赖 FastAPI）。

- 密码：scrypt；账号不存在时也走一次 dummy 校验，统一 401。
- session：24h 绝对过期；登录轮换（撤销该客户全部旧 session）；只存 token 哈希。
- 不创建/关闭业务会话；会话归属 `backend/conversations/`，由 API 层编排。
- 登录与恢复只 flush，调用方负责提交；登出自行提交。
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.passwords import verify_dummy_password, verify_password
from backend.identity.rate_limit import RateLimitedError as RateLimitedError
from backend.identity.rate_limit import consume_fixed_window
from backend.identity.tokens import hash_token as hash_token
from backend.identity.tokens import utc_now as utc_now
from backend.platform.models import ServiceCustomer, ServiceCustomerSession

CUSTOMER_SESSION_TTL = timedelta(hours=24)
LOGIN_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)
CUSTOMER_COOKIE = "csid"


class InvalidSessionError(Exception):
    """session 不存在、已撤销或账号不可用。"""


class ExpiredSessionError(Exception):
    """session 已过期；与 InvalidSession 分开，便于返回不同错误码。"""


@dataclass(frozen=True)
class Customer:
    id: str
    tenant_id: str
    username: str
    display_name: str


@dataclass(frozen=True)
class CustomerLogin:
    token: str
    customer: Customer
    expires_at: datetime
    session_id: str


@dataclass(frozen=True)
class ResolvedCustomerSession:
    customer: Customer
    expires_at: datetime
    session_id: str


async def _check_login_rate_limit(db: AsyncSession, username: str, ip: str) -> None:
    """固定窗口 5/15min；先写桶再校验业务，超限直接 429。"""
    await consume_fixed_window(
        db,
        bucket_key=f"customer_login:{username.strip().lower()}:{ip}",
        limit=LOGIN_LIMIT,
        window=LOGIN_WINDOW,
        now=utc_now(),
    )


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
    session_id = str(uuid4())
    db.add(
        ServiceCustomerSession(
            id=session_id,
            customer_id=row.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=expires_at,
        )
    )
    await db.flush()
    return CustomerLogin(
        token=token,
        customer=_customer(row),
        expires_at=expires_at,
        session_id=session_id,
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
    await db.flush()
    return ResolvedCustomerSession(
        customer=_customer(customer),
        expires_at=row.expires_at,
        session_id=row.id,
    )


async def revoke_customer_session(db: AsyncSession, token: str) -> None:
    """撤销当前 session，只 flush；供登出路由与审计同事务提交。"""
    now = utc_now()
    await db.execute(
        update(ServiceCustomerSession)
        .where(
            ServiceCustomerSession.token_hash == hash_token(token),
            ServiceCustomerSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.flush()


async def logout_customer(db: AsyncSession, token: str) -> None:
    """撤销当前 session；无 cookie 或已失效也返回成功（幂等登出）。"""
    await revoke_customer_session(db, token)
    await db.commit()
