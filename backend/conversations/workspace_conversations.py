"""坐席工作台：会话归属门禁、待接入队列与条件领取。

- 归属读取只允许同租户且 `assigned_employee_id` 为本人的会话；其余返回 None。
- 队列只返回同租户 `status='QUEUED'` 的交接单，按 `created_at, id` 升序。
- 队列摘要在读取时派生：客户账号/显示名、等待秒数、原因、订单数、脱敏末条；
  不返回完整消息或交接单上下文（plan 3.3.5）。
- 领取是条件写：只有 `QUEUED` 交接单能被领取，同事务把会话归属写给本人；
  本模块只 flush/execute，由 API 层统一 commit，失败由调用方回滚。
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ScalarSelect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.handoffs import redact_text
from backend.conversations.statuses import CLAIMED, CLOSED, QUEUED
from backend.platform.models import (
    ServiceConversation,
    ServiceCustomer,
    ServiceHandoff,
    ServiceMessage,
)

QUEUE_LAST_MESSAGE_CHAR_LIMIT = 100


class ClaimConflictError(Exception):
    """交接单已不再是 `QUEUED`：被其他坐席领取或状态已变化。"""


class HandoffClosedError(Exception):
    """交接单已关闭，不再接受领取；对应 409 `CONVERSATION_CLOSED`。"""


@dataclass(frozen=True)
class WorkspaceConversation:
    id: str
    status: str


@dataclass(frozen=True)
class ClaimedHandoff:
    handoff_id: str
    conversation_id: str
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


async def claim_handoff(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    handoff_id: str,
) -> ClaimedHandoff | None:
    """条件领取：并发下只有一个事务能把同一交接单从 `QUEUED` 改为 `CLAIMED`。

    - 不存在或跨租户返回 None（API 映射 404，不区分“不存在”与“无权”）。
    - 已关闭抛 `HandoffClosedError`，其余非 `QUEUED` 抛 `ClaimConflictError`。
    - 先读状态是为了给出可区分的错误码；真正防竞态的是带 `status='QUEUED'`
      的 `UPDATE ... RETURNING`。Postgres 在行锁释放后重新评估条件，影响 0 行
      即说明另一个事务已领取。
    - 同事务把会话改为 `CLAIMED` 并写 `assigned_employee_id`；不写系统消息与审计
      （分别由接管 F-08、审计 F-13 负责）。
    """
    row = (
        await db.execute(
            select(ServiceHandoff.status, ServiceHandoff.conversation_id).where(
                ServiceHandoff.id == handoff_id,
                ServiceHandoff.tenant_id == tenant_id,
            )
        )
    ).one_or_none()
    if row is None:
        return None

    status, conversation_id = row
    if status == CLOSED:
        raise HandoffClosedError
    if status != QUEUED:
        raise ClaimConflictError

    now = utc_now()
    claimed = (
        await db.execute(
            update(ServiceHandoff)
            .where(
                ServiceHandoff.id == handoff_id,
                ServiceHandoff.tenant_id == tenant_id,
                ServiceHandoff.status == QUEUED,
            )
            .values(
                status=CLAIMED,
                claimed_by=employee_id,
                claimed_at=now,
                version=ServiceHandoff.version + 1,
                updated_at=now,
            )
            .returning(ServiceHandoff.id)
        )
    ).scalar_one_or_none()
    if claimed is None:
        raise ClaimConflictError

    conversation = (
        await db.execute(
            update(ServiceConversation)
            .where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.status == QUEUED,
            )
            .values(
                status=CLAIMED,
                assigned_employee_id=employee_id,
                updated_at=now,
            )
            .returning(ServiceConversation.id)
        )
    ).scalar_one_or_none()
    if conversation is None:
        # 交接单与会话状态应由 F-03 同事务维护；出现分歧时整体回滚，不留下半领取。
        raise ClaimConflictError

    return ClaimedHandoff(
        handoff_id=handoff_id,
        conversation_id=conversation_id,
        status=CLAIMED,
    )
