"""员工认证与 session（不依赖 FastAPI）。

- 密码：scrypt；账号不存在时也走一次 dummy 校验，统一 401。
- session：8h 绝对过期；登录轮换（撤销该员工全部旧 session）；只存 token 哈希。
- 角色不是 `agent` 时抛 `ForbiddenRoleError`，不创建 session。
- 只 flush；调用方负责提交。
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity.passwords import verify_dummy_password, verify_password
from backend.identity.rate_limit import RateLimitedError, consume_fixed_window
from backend.identity.tokens import hash_token, utc_now
from backend.platform.models import ServiceEmployee, ServiceEmployeeSession

EMPLOYEE_SESSION_TTL = timedelta(hours=8)
LOGIN_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)
EMPLOYEE_COOKIE = "esid"
AGENT_ROLE = "agent"

__all__ = [
    "AGENT_ROLE",
    "EMPLOYEE_COOKIE",
    "EMPLOYEE_SESSION_TTL",
    "ExpiredSessionError",
    "ForbiddenRoleError",
    "InvalidSessionError",
    "Employee",
    "EmployeeLogin",
    "RateLimitedError",
    "ResolvedEmployeeSession",
    "hash_token",
    "login_employee",
    "logout_employee",
    "resolve_employee_session",
    "utc_now",
]


class InvalidSessionError(Exception):
    """session 不存在、已撤销或账号不可用。"""


class ExpiredSessionError(Exception):
    """session 已过期；与 InvalidSession 分开，便于返回不同错误码。"""


class ForbiddenRoleError(Exception):
    """员工角色不是 `agent`；M1 只允许坐席访问工作台。"""


@dataclass(frozen=True)
class Employee:
    id: str
    tenant_id: str
    username: str
    display_name: str
    role: str


@dataclass(frozen=True)
class EmployeeLogin:
    token: str
    employee: Employee
    expires_at: datetime


@dataclass(frozen=True)
class ResolvedEmployeeSession:
    employee: Employee
    expires_at: datetime


async def _lookup_employee(
    db: AsyncSession, tenant_id: str, username: str
) -> ServiceEmployee | None:
    statement = select(ServiceEmployee).where(
        ServiceEmployee.tenant_id == tenant_id,
        ServiceEmployee.username == username.strip(),
        ServiceEmployee.active.is_(True),
    )
    return (await db.execute(statement)).scalar_one_or_none()


def _employee(row: ServiceEmployee) -> Employee:
    return Employee(
        id=row.id,
        tenant_id=row.tenant_id,
        username=row.username,
        display_name=row.display_name,
        role=row.role,
    )


async def login_employee(
    db: AsyncSession,
    tenant_id: str,
    username: str,
    password: str,
    client_ip: str,
) -> EmployeeLogin | None:
    """凭据正确返回登录结果；失败返回 None。非 agent 抛 `ForbiddenRoleError`。"""
    await consume_fixed_window(
        db,
        bucket_key=f"employee_login:{username.strip().lower()}:{client_ip}",
        limit=LOGIN_LIMIT,
        window=LOGIN_WINDOW,
        now=utc_now(),
    )
    row = await _lookup_employee(db, tenant_id, username)
    if row is None:
        verify_dummy_password(password)
        return None
    if not verify_password(password, row.password_hash):
        return None
    if row.role != AGENT_ROLE:
        raise ForbiddenRoleError

    now = utc_now()
    token = secrets.token_urlsafe(32)
    # 登录轮换：撤销该员工全部旧 session，旧 cookie 立即 401。
    await db.execute(
        update(ServiceEmployeeSession)
        .where(
            ServiceEmployeeSession.employee_id == row.id,
            ServiceEmployeeSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    expires_at = now + EMPLOYEE_SESSION_TTL
    db.add(
        ServiceEmployeeSession(
            id=str(uuid4()),
            employee_id=row.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=expires_at,
        )
    )
    await db.flush()
    return EmployeeLogin(token=token, employee=_employee(row), expires_at=expires_at)


async def resolve_employee_session(
    db: AsyncSession, tenant_id: str, token: str
) -> ResolvedEmployeeSession:
    """按 cookie token 恢复员工；失效抛 401 类异常，角色不符抛 403 类异常。"""
    now = utc_now()
    statement = select(ServiceEmployeeSession).where(
        ServiceEmployeeSession.token_hash == hash_token(token)
    )
    row = (await db.execute(statement)).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise InvalidSessionError
    if row.expires_at <= now:
        raise ExpiredSessionError
    employee = await db.get(ServiceEmployee, row.employee_id)
    if employee is None or not employee.active or employee.tenant_id != tenant_id:
        raise InvalidSessionError
    if employee.role != AGENT_ROLE:
        raise ForbiddenRoleError
    return ResolvedEmployeeSession(employee=_employee(employee), expires_at=row.expires_at)


async def logout_employee(db: AsyncSession, token: str) -> None:
    """撤销当前 session；无 cookie 或已失效也返回成功（幂等登出）。"""
    now = utc_now()
    await db.execute(
        update(ServiceEmployeeSession)
        .where(
            ServiceEmployeeSession.token_hash == hash_token(token),
            ServiceEmployeeSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await db.commit()
