"""会话状态变更的共享写操作：系统消息、幂等重放、open 交接单终态化。

客户关闭（F-11）与坐席关闭/转回（F-12）共用同一套写语义：

- 状态回执是一条系统消息；`idempotency_key` 由调用方提供，`author_id` 记录动作人
  （客户动作为 `None`，坐席动作为员工 id）。
- 重放按「会话 + 键 + 动作人」命中：同一键不能跨动作者重放，避免他人用别人的键
  读到动作结果（plan 5.1 的 ownership 要求）。
- open 交接单终态化不重写 `pending_step`：它是转人工时点的快照（plan 3.3.4）。
- 本模块只 flush，由 API 层统一 commit；失败由调用方回滚。
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.statuses import CLOSED, OPEN_HANDOFF_STATUSES
from backend.platform.models import ServiceHandoff, ServiceMessage


async def replay_system_message(
    db: AsyncSession,
    conversation_id: str,
    idempotency_key: str,
    *,
    author_id: str | None = None,
) -> ServiceMessage | None:
    """同一动作者的同一幂等键重放：返回首次状态变更的系统消息。"""
    statement = select(ServiceMessage).where(
        ServiceMessage.conversation_id == conversation_id,
        ServiceMessage.author_type == "system",
        ServiceMessage.idempotency_key == idempotency_key,
    )
    if author_id is None:
        statement = statement.where(ServiceMessage.author_id.is_(None))
    else:
        statement = statement.where(ServiceMessage.author_id == author_id)
    return (await db.execute(statement)).scalar_one_or_none()


async def close_open_handoffs(
    db: AsyncSession, tenant_id: str, conversation_id: str, now: datetime
) -> None:
    """终态化同一会话的所有 open 交接单；`pending_step` 保持原值。"""
    await db.execute(
        update(ServiceHandoff)
        .where(
            ServiceHandoff.tenant_id == tenant_id,
            ServiceHandoff.conversation_id == conversation_id,
            ServiceHandoff.status.in_(OPEN_HANDOFF_STATUSES),
        )
        .values(
            status=CLOSED,
            version=ServiceHandoff.version + 1,
            updated_at=now,
        )
    )


async def write_system_message(
    db: AsyncSession,
    *,
    conversation_id: str,
    content: str,
    idempotency_key: str,
    trace_id: str,
    now: datetime,
    author_id: str | None = None,
) -> ServiceMessage:
    """写一条状态回执系统消息；`author_id` 用于重放时区分动作人。"""
    notice = ServiceMessage(
        conversation_id=conversation_id,
        author_type="system",
        author_id=author_id,
        content=content,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(notice)
    await db.flush()
    return notice
