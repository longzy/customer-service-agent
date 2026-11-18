"""客户关闭会话：任意未关闭状态可关闭，同事务终态交接单（plan 3.3.1/3.4）。

- 关闭是幂等的条件状态转换：只有把会话从非 `CLOSED` 改为 `CLOSED` 的那一次写
  “会话已结束”系统消息；重复关闭返回当前游标，不重写 `closed_at`。
- 先更新交接单、再条件更新会话：与领取/接管相同的 `handoff → conversation`
  加锁顺序，避免“客户关闭 vs 坐席领取”并发时交叉等待。
- 本模块只 flush，由 API 层统一 commit；失败由调用方回滚。
"""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.customer_chat import ChatResult, view_message
from backend.conversations.customer_conversations import latest_message_id
from backend.conversations.statuses import CLOSED, OPEN_HANDOFF_STATUSES
from backend.platform.models import ServiceConversation, ServiceHandoff, ServiceMessage

CLOSED_NOTICE = "会话已结束"


class ConversationCloseConflictError(Exception):
    """会话已不是未关闭状态，但本次仍有 open 交接单被改；防御性回滚。"""


async def close_customer_conversation(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    trace_id: str,
    now: datetime,
) -> ChatResult:
    """关闭客户当前会话；交接单先终态化，再条件关闭会话。

    `conversation` 可能是刚读到的 open 会话，也可能是已关闭的最近会话（重放）。
    只有真正发生状态转换时才写系统消息；重复关闭返回空增量页。
    """
    closed_handoffs = (
        (
            await db.execute(
                update(ServiceHandoff)
                .where(
                    ServiceHandoff.tenant_id == conversation.tenant_id,
                    ServiceHandoff.conversation_id == conversation.id,
                    ServiceHandoff.status.in_(OPEN_HANDOFF_STATUSES),
                )
                .values(
                    status=CLOSED,
                    pending_step=CLOSED_NOTICE,
                    version=ServiceHandoff.version + 1,
                    updated_at=now,
                )
                .returning(ServiceHandoff.id)
            )
        )
        .scalars()
        .all()
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
        if closed_handoffs:
            # 会话已被并发关闭却还有 open 交接单：数据分歧，整体回滚不留半关闭。
            raise ConversationCloseConflictError
        return ChatResult(
            conversation_id=conversation.id,
            status=CLOSED,
            messages=[],
            after_id=await latest_message_id(db, conversation.id),
        )

    notice = ServiceMessage(
        conversation_id=conversation.id,
        author_type="system",
        author_id=None,
        content=CLOSED_NOTICE,
        idempotency_key=None,
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
