"""坐席工作台只读查询：会话归属门禁与待接入队列。

- 归属读取只允许同租户且 `assigned_employee_id` 为本人的会话；其余返回 None。
- 队列只返回同租户 `status='QUEUED'` 的交接单，按 `created_at, id` 升序。
- 队列摘要在读取时派生：客户账号/显示名、等待秒数、原因、订单数、脱敏末条；
  不返回完整消息或交接单上下文（plan 3.3.5）。
- 本模块只读，不提交事务，不改变交接单归属。
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ScalarSelect, select
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


def _last_customer_message() -> ScalarSelect[str]:
    """相关标量子查询：每个会话最后一条客户消息；系统“排队中”提示不占用摘要。"""
    return (
        select(ServiceMessage.content)
        .where(
            ServiceMessage.conversation_id == ServiceHandoff.conversation_id,
            ServiceMessage.author_type == "customer",
        )
        .order_by(ServiceMessage.id.desc())
        .limit(1)
        .correlate(ServiceHandoff)
        .scalar_subquery()
    )


async def list_queued_handoffs(db: AsyncSession, tenant_id: str) -> list[QueueItem]:
    statement = (
        select(ServiceHandoff, ServiceCustomer, _last_customer_message())
        .join(ServiceCustomer, ServiceCustomer.id == ServiceHandoff.customer_id)
        .where(
            ServiceHandoff.tenant_id == tenant_id,
            ServiceHandoff.status == QUEUED,
            ServiceCustomer.tenant_id == tenant_id,
        )
        .order_by(ServiceHandoff.created_at, ServiceHandoff.id)
    )
    rows = (await db.execute(statement)).all()
    now = utc_now()
    return [
        QueueItem(
            handoff_id=handoff.id,
            conversation_id=handoff.conversation_id,
            customer_username=customer.username,
            customer_display_name=customer.display_name,
            waiting_seconds=_waiting_seconds(handoff.created_at, now),
            reason=handoff.reason,
            # plan 3.3.5：本切片无订单 Tool，队列摘要的 order_count 恒为 0。
            order_count=0,
            last_message=redact_text(last_message or "")[:QUEUE_LAST_MESSAGE_CHAR_LIMIT],
        )
        for handoff, customer, last_message in rows
    ]
