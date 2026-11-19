"""客户关闭会话：任意未关闭状态可关闭，同事务终态交接单（plan 3.3.1/3.4）。

- 关闭是条件状态转换：只有把会话从非 `CLOSED` 改为 `CLOSED` 的那次成功写
  “会话已结束”系统消息；会话已关闭且不是同键重放时返回 409（plan 3.3.1）。
- 同一 `Idempotency-Key` 重放返回首次关闭的系统消息，不产生第二条消息（INV-07）；
  重放不是新的写操作，与“CLOSED 上任意写 409”不冲突。
- 先更新交接单、再条件更新会话：与领取/接管相同的 `handoff → conversation`
  加锁顺序，避免“客户关闭 vs 坐席领取”并发时交叉等待。
- 交接单 `pending_step` 保持原值：待办语义由 F-12 统一定义（F-10 D-5）。
- 系统消息、幂等重放与交接单终态化复用 `state_changes`，与坐席关闭/转回同语义。
- 本模块只 flush，由 API 层统一 commit；失败由调用方回滚。
"""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.customer_chat import (
    ChatResult,
    ConversationClosedError,
    view_message,
)
from backend.conversations.state_changes import (
    close_open_handoffs,
    replay_system_message,
    write_system_message,
)
from backend.conversations.statuses import CLOSED
from backend.platform.models import ServiceConversation, ServiceMessage

CLOSED_NOTICE = "会话已结束"


def _closed_result(
    conversation_id: str, notice: ServiceMessage, *, replayed: bool = False
) -> ChatResult:
    return ChatResult(
        conversation_id=conversation_id,
        status=CLOSED,
        messages=[view_message(notice)],
        after_id=notice.id,
        replayed=replayed,
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
    replay = await replay_system_message(db, conversation.id, idempotency_key)
    if replay is not None:
        return _closed_result(conversation.id, replay, replayed=True)
    if conversation.status == CLOSED:
        raise ConversationClosedError

    await close_open_handoffs(db, conversation.tenant_id, conversation.id, now)

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
        replay = await replay_system_message(db, conversation.id, idempotency_key)
        if replay is not None:
            return _closed_result(conversation.id, replay, replayed=True)
        raise ConversationClosedError

    notice = await write_system_message(
        db,
        conversation_id=conversation.id,
        content=CLOSED_NOTICE,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        now=now,
    )
    return _closed_result(conversation.id, notice)
