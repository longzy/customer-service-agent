"""坐席工作台只读查询：会话归属门禁与待接入队列。

- 归属读取只允许同租户且 `assigned_employee_id` 为本人的会话；其余返回 None。
- 队列只返回同租户 `status='QUEUED'` 的交接单，按 `created_at, id` 升序。
- 队列摘要在读取时派生：客户账号/显示名、等待秒数、原因、订单数、脱敏末条；
  不返回完整消息或交接单上下文（plan 3.3.5）。
- 本模块只读，不提交事务，不改变交接单归属。
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.handoffs import redact_text
from backend.conversations.statuses import QUEUED
from backend.platform.models import (
    ServiceConversation,
    ServiceCustomer,
    ServiceHandoff,
    ServiceMessage,
)

QUEUE_LAST_MESSAGE_CHAR_LIMIT = 100


@dataclass(frozen=True)
class WorkspaceConversation:
    id: str
    status: str


@dataclass(frozen=True)
class QueueItem:
    handoff_id: str
    conversation_id: str
    customer_username: str
    customer_display_name: str
    waiting_seconds: int
    reason: str
    order_count: int
    last_message: str


def utc_now() -> datetime:
    return datetime.now(UTC)


async def get_assigned_conversation(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
) -> WorkspaceConversation | None:
    statement = select(ServiceConversation).where(
        ServiceConversation.id == conversation_id,
        ServiceConversation.tenant_id == tenant_id,
        ServiceConversation.assigned_employee_id == employee_id,
    )
    row = (await db.execute(statement)).scalar_one_or_none()
    if row is None:
        return None
    return WorkspaceConversation(id=row.id, status=row.status)


def _waiting_seconds(created_at: datetime, now: datetime) -> int:
    return max(0, int((now - created_at).total_seconds()))


def _order_count(context: object) -> int:
    if not isinstance(context, dict):
        return 0
    value = context.get("order_count", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, value)


async def _last_customer_messages(db: AsyncSession, conversation_ids: list[str]) -> dict[str, str]:
    """每个会话最后一条客户消息；系统“排队中”提示不占用队列摘要。"""
    if not conversation_ids:
        return {}
    rows = (
        await db.execute(
            select(ServiceMessage.conversation_id, ServiceMessage.content)
            .where(
                ServiceMessage.conversation_id.in_(conversation_ids),
                ServiceMessage.author_type == "customer",
            )
            # PostgreSQL DISTINCT ON：每个会话只取最后一条客户消息，不把整段历史读进内存。
            .ext(distinct_on(ServiceMessage.conversation_id))
            .order_by(ServiceMessage.conversation_id, ServiceMessage.id.desc())
        )
    ).all()
    return {conversation_id: content for conversation_id, content in rows}


async def list_queued_handoffs(db: AsyncSession, tenant_id: str) -> list[QueueItem]:
    statement = (
        select(ServiceHandoff, ServiceCustomer)
        .join(ServiceCustomer, ServiceCustomer.id == ServiceHandoff.customer_id)
        .where(
            ServiceHandoff.tenant_id == tenant_id,
            ServiceHandoff.status == QUEUED,
            ServiceCustomer.tenant_id == tenant_id,
        )
        .order_by(ServiceHandoff.created_at, ServiceHandoff.id)
    )
    rows = (await db.execute(statement)).all()
    last_messages = await _last_customer_messages(
        db, [handoff.conversation_id for handoff, _customer in rows]
    )
    now = utc_now()
    return [
        QueueItem(
            handoff_id=handoff.id,
            conversation_id=handoff.conversation_id,
            customer_username=customer.username,
            customer_display_name=customer.display_name,
            waiting_seconds=_waiting_seconds(handoff.created_at, now),
            reason=handoff.reason,
            order_count=_order_count(handoff.context),
            last_message=redact_text(last_messages.get(handoff.conversation_id, ""))[
                :QUEUE_LAST_MESSAGE_CHAR_LIMIT
            ],
        )
        for handoff, customer in rows
    ]
