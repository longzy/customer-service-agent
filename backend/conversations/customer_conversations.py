"""客户会话的读取与恢复；归属 conversations 模块，不放在 identity。

- 一个客户同时只有一个未关闭会话。
- AI_ACTIVE 空闲 24h 在登录/读状态时惰性关闭，不引入后台 worker。
- 调用方负责提交事务；本模块只 flush。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.platform.models import ServiceConversation, ServiceMessage

CONVERSATION_IDLE_TIMEOUT = timedelta(hours=24)
STATUS_AI_ACTIVE = "AI_ACTIVE"
STATUS_CLOSED = "CLOSED"


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


async def get_open_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str
) -> ServiceConversation | None:
    """只读当前未关闭会话；不存在时返回 None，由调用方决定 404/409。"""
    return await _open_conversation(db, tenant_id, customer_id)


async def get_or_create_open_conversation(
    db: AsyncSession, tenant_id: str, customer_id: str, now: datetime
) -> CustomerConversation:
    """返回该客户未关闭会话；没有或 AI 空闲超时则新建。"""
    existing = await _open_conversation(db, tenant_id, customer_id)
    if existing is not None:
        stale = (
            existing.status == STATUS_AI_ACTIVE
            and existing.last_activity_at + CONVERSATION_IDLE_TIMEOUT <= now
        )
        if not stale:
            return view(existing, await latest_message_id(db, existing.id))
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
    return view(created, 0)


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
