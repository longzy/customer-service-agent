"""客户关闭会话：任意未关闭状态可关闭，同事务终态交接单（plan 3.3.1/3.4）。

- 关闭是条件状态转换：只有把会话从非 `CLOSED` 改为 `CLOSED` 的那次成功写
  “会话已结束”系统消息；会话已关闭且不是同键重放时返回 409（plan 3.3.1）。
- 同一 `Idempotency-Key` 重放返回首次关闭的系统消息，不产生第二条消息（INV-07）；
  重放不是新的写操作，与“CLOSED 上任意写 409”不冲突。
- 先更新交接单、再条件更新会话：与领取/接管相同的 `handoff → conversation`
  加锁顺序，避免“客户关闭 vs 坐席领取”并发时交叉等待。
- 交接单 `pending_step` 保持原值：待办语义由 F-12 统一定义（F-10 D-5）。
- 本模块只 flush，由 API 层统一 commit；失败由调用方回滚。
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.customer_chat import (
    ChatResult,
    ConversationClosedError,
    view_message,
)
from backend.conversations.statuses import CLOSED, OPEN_HANDOFF_STATUSES
from backend.platform.models import ServiceConversation, ServiceHandoff, ServiceMessage

CLOSED_NOTICE = "会话已结束"


async def _replay(
    db: AsyncSession, conversation_id: str, idempotency_key: str
) -> ChatResult | None:
    """同一幂等键重放：返回首次关闭的系统消息。"""
    row = (
        await db.execute(
            select(ServiceMessage).where(
                ServiceMessage.conversation_id == conversation_id,
                ServiceMessage.author_type == "system",
                ServiceMessage.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return ChatResult(
        conversation_id=conversation_id,
        status=CLOSED,
        messages=[view_message(row)],
        after_id=row.id,
    )


async def close_customer_conversation(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    idempotency_key: str,
    trace_id: str,
    now: datetime,
) -> ChatResult:
    """关闭客户当前会话；交接单先终态化，再条件关闭会话。

    `conversation` 可能是 open 会话，也可能是最近一条已关闭会话（同键重放）。
    已关闭且无重放记录时抛 `ConversationClosedError`（409）。
    """
    replay = await _replay(db, conversation.id, idempotency_key)
    if replay is not None:
        return replay
    if conversation.status == CLOSED:
        raise ConversationClosedError

    await db.execute(
        update(ServiceHandoff)
        .where(
            ServiceHandoff.tenant_id == conversation.tenant_id,
            ServiceHandoff.conversation_id == conversation.id,
            ServiceHandoff.status.in_(OPEN_HANDOFF_STATUSES),
        )
        .values(
            status=CLOSED,
            version=ServiceHandoff.version + 1,
            updated_at=now,
        )
    )

    closed = (
        await db.execute(
            update(ServiceConversation)
            .where(
                ServiceConversation.id == conversation.id,
                ServiceConversation.tenant_id == conversation.tenant_id,
                ServiceConversation.customer_id == conversation.customer_id,
                ServiceConversation.status != CLOSED,
            )
            .values(status=CLOSED, closed_at=now, updated_at=now)
            .returning(ServiceConversation.id)
        )
    ).scalar_one_or_none()

    if closed is None:
        # 并发关闭：另一个事务先提交。同键重放返回首次消息，否则按 plan 409。
        replay = await _replay(db, conversation.id, idempotency_key)
        if replay is not None:
            return replay
        raise ConversationClosedError

    notice = ServiceMessage(
        conversation_id=conversation.id,
        author_type="system",
        author_id=None,
        content=CLOSED_NOTICE,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(notice)
    await db.flush()
    return ChatResult(
        conversation_id=conversation.id,
        status=CLOSED,
        messages=[view_message(notice)],
        after_id=notice.id,
    )
