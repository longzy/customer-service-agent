"""客户会话的读取与恢复；归属 conversations 模块，不放在 identity。

- 一个客户同时只有一个未关闭会话。
- AI_ACTIVE 空闲 24h 在登录、读状态、发消息时惰性关闭，不引入后台 worker。
- 调用方负责提交事务；本模块只 flush。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.statuses import AI_ACTIVE, CLOSED
from backend.platform.models import ServiceConversation, ServiceMessage

CONVERSATION_IDLE_TIMEOUT = timedelta(hours=24)


@dataclass(frozen=True)
class CustomerConversation:
    id: str
    status: str
    after_id: int


def view(row: ServiceConversation, after_id: int) -> CustomerConversation:
    return CustomerConversation(id=row.id, status=row.status, after_id=after_id)


async def latest_message_id(db: AsyncSession, conversation_id: str) -> int:
    value = await db.scalar(
        select(func.max(ServiceMessage.id)).where(ServiceMessage.conversation_id == conversation_id)
    )
    return int(value or 0)


async def _find_open(
    db: AsyncSession, tenant_id: str, customer_id: str
) -> ServiceConversation | None:
    statement = (
        select(ServiceConversation)
        .where(
            ServiceConversation.tenant_id == tenant_id,
            ServiceConversation.customer_id == customer_id,
            ServiceConversation.status != CLOSED,
        )
        .order_by(ServiceConversation.created_at.desc())
        .limit(1)
    )
    return (await db.execute(statement)).scalar_one_or_none()


async def get_open_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str
) -> ServiceConversation | None:
    """当前未关闭会话；不存在时返回 None（可能已关闭）。"""
    return await _find_open(db, tenant_id, customer_id)


async def get_latest_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str
) -> ServiceConversation | None:
    """最近一条会话，含已关闭；用于读历史。"""
    statement = (
        select(ServiceConversation)
        .where(
            ServiceConversation.tenant_id == tenant_id,
            ServiceConversation.customer_id == customer_id,
        )
        .order_by(ServiceConversation.created_at.desc())
        .limit(1)
    )
    return (await db.execute(statement)).scalar_one_or_none()


async def get_current_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str
) -> ServiceConversation | None:
    """当前未关闭会话；没有时返回最近一条（含已关闭）。

    读历史与关闭重放都从同一条当前会话出发，避免调用方各写一遍 open→latest 兜底。
    """
    open_row = await _find_open(db, tenant_id, customer_id)
    if open_row is not None:
        return open_row
    return await get_latest_conversation(db, tenant_id, customer_id)


def _is_stale(row: ServiceConversation, now: datetime) -> bool:
    return row.status == AI_ACTIVE and row.last_activity_at + CONVERSATION_IDLE_TIMEOUT <= now


def _close(row: ServiceConversation, now: datetime) -> None:
    row.status = CLOSED
    row.closed_at = now
    row.updated_at = now


async def _create(
    db: AsyncSession, tenant_id: str, customer_id: str, now: datetime
) -> ServiceConversation:
    created = ServiceConversation(
        id=str(uuid4()),
        tenant_id=tenant_id,
        customer_id=customer_id,
        status=AI_ACTIVE,
        journey_id=str(uuid4()),
        created_at=now,
        updated_at=now,
        last_activity_at=now,
    )
    db.add(created)
    await db.flush()
    return created


async def get_sendable_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str, now: datetime
) -> ServiceConversation | None:
    """发消息用：AI_ACTIVE 空闲超时就关闭并新建；显式关闭返回 None。"""
    existing = await _find_open(db, tenant_id, customer_id)
    if existing is None:
        return None
    if not _is_stale(existing, now):
        return existing
    _close(existing, now)
    await db.flush()
    return await _create(db, tenant_id, customer_id, now)


async def get_or_create_open_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str, now: datetime
) -> CustomerConversation:
    """登录/读状态用：没有未关闭会话或 AI 空闲超时则新建。"""
    sendable = await get_sendable_conversation(db, tenant_id, customer_id, now)
    row = sendable or await _create(db, tenant_id, customer_id, now)
    return view(row, await latest_message_id(db, row.id))


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
    if row is None:
        return None
    return view(row, await latest_message_id(db, row.id))
