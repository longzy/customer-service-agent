"""坐席关闭会话与转回 AI（plan 3.3.1/3.4）。

- 关闭：`CLAIMED`/`HUMAN_ACTIVE` 可关闭；open 交接单同事务终态化，写“会话已结束”。
- 转回 AI：只允许 `HUMAN_ACTIVE`；会话回 `AI_ACTIVE`、清空 `assigned_employee_id`、
  open 交接单终态化，写“已转回 AI 客服”。客户在同一会话继续对话，历史不丢。
- 错误按**会话实际状态**判定，不看交接单状态（F-07 建议）：会话已关闭 → 409
  `CONVERSATION_CLOSED`；不存在/他人/跨租户/状态不可操作 → None（API 404）。
- 幂等：同一 `Idempotency-Key` 重放返回首次系统消息；`status` 取会话当前状态。
  重放先于归属与状态检查：转回会清空 assignment，否则重放会被误判 404。
- 锁顺序：先更新交接单、再条件更新会话，与领取/接管/客户关闭一致，避免交叉等待。
- 交接单 `pending_step` 保持创建时快照，不重写（F-11 D-4；本卡 D-6）。
- 本模块只 flush，由 API 层统一 commit；失败由调用方回滚。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.customer_chat import MessageView, view_message
from backend.conversations.customer_close import CLOSED_NOTICE
from backend.conversations.statuses import (
    AI_ACTIVE,
    CLAIMED,
    CLOSED,
    HUMAN_ACTIVE,
    OPEN_HANDOFF_STATUSES,
)
from backend.platform.models import ServiceConversation, ServiceHandoff, ServiceMessage

RETURNED_TO_AI_NOTICE = "已转回 AI 客服"
CLOSABLE_STATUSES = (CLAIMED, HUMAN_ACTIVE)


class ConversationClosedError(Exception):
    """会话已关闭，不再接受坐席写操作；对应 409 `CONVERSATION_CLOSED`。"""


@dataclass(frozen=True)
class AgentStateChange:
    """坐席状态变更回执：系统消息即前端的状态与提示来源。"""

    conversation_id: str
    status: str
    message: MessageView


async def _find_conversation(
    db: AsyncSession, tenant_id: str, conversation_id: str
) -> ServiceConversation | None:
    """同租户会话；不先按归属过滤，重放需要在转回清空 assignment 后仍可命中。"""
    return (
        await db.execute(
            select(ServiceConversation).where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()


async def _replay(
    db: AsyncSession, conversation_id: str, idempotency_key: str
) -> ServiceMessage | None:
    """同一幂等键重放：返回首次状态变更的系统消息。"""
    return (
        await db.execute(
            select(ServiceMessage).where(
                ServiceMessage.conversation_id == conversation_id,
                ServiceMessage.author_type == "system",
                ServiceMessage.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()


async def _current_status(db: AsyncSession, tenant_id: str, conversation_id: str) -> str | None:
    return (
        await db.execute(
            select(ServiceConversation.status).where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()


async def _finish_open_handoffs(
    db: AsyncSession, conversation: ServiceConversation, now: datetime
) -> None:
    """终态化同一会话的所有 open 交接单；不重写 `pending_step`。"""
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


async def _write_notice(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    content: str,
    idempotency_key: str,
    trace_id: str,
    now: datetime,
) -> ServiceMessage:
    notice = ServiceMessage(
        conversation_id=conversation.id,
        author_type="system",
        author_id=None,
        content=content,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(notice)
    await db.flush()
    return notice


def _result(conversation_id: str, status: str, message: ServiceMessage) -> AgentStateChange:
    return AgentStateChange(
        conversation_id=conversation_id,
        status=status,
        message=view_message(message),
    )


async def close_conversation_by_agent(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
    *,
    idempotency_key: str,
    trace_id: str,
    now: datetime,
) -> AgentStateChange | None:
    """坐席关闭 `CLAIMED`/`HUMAN_ACTIVE` 会话；已关闭 409，其余不可操作 404。"""
    conversation = await _find_conversation(db, tenant_id, conversation_id)
    if conversation is None:
        return None

    replay = await _replay(db, conversation_id, idempotency_key)
    if replay is not None:
        # 重放时状态取会话当前值：客户可能在坐席动作之后又关闭了会话。
        return _result(conversation_id, conversation.status, replay)

    if conversation.assigned_employee_id != employee_id:
        return None
    if conversation.status == CLOSED:
        raise ConversationClosedError
    if conversation.status not in CLOSABLE_STATUSES:
        return None

    await _finish_open_handoffs(db, conversation, now)
    changed = (
        await db.execute(
            update(ServiceConversation)
            .where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
                ServiceConversation.status.in_(CLOSABLE_STATUSES),
            )
            .values(status=CLOSED, closed_at=now, updated_at=now)
            .returning(ServiceConversation.id)
        )
    ).scalar_one_or_none()
    if changed is None:
        # 读取后被并发关闭/转回：按最新状态给 409 或 404，不留下半写。
        status = await _current_status(db, tenant_id, conversation_id)
        if status is None:
            return None
        if status == CLOSED:
            raise ConversationClosedError
        return None

    notice = await _write_notice(
        db,
        conversation,
        content=CLOSED_NOTICE,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        now=now,
    )
    return _result(conversation_id, CLOSED, notice)


async def return_conversation_to_ai(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
    *,
    idempotency_key: str,
    trace_id: str,
    now: datetime,
) -> AgentStateChange | None:
    """接管坐席把 `HUMAN_ACTIVE` 会话转回 AI；其余可操作状态 404。"""
    conversation = await _find_conversation(db, tenant_id, conversation_id)
    if conversation is None:
        return None

    replay = await _replay(db, conversation_id, idempotency_key)
    if replay is not None:
        # 重放时状态取会话当前值：客户可能在坐席动作之后又关闭了会话。
        return _result(conversation_id, conversation.status, replay)

    if conversation.assigned_employee_id != employee_id:
        return None
    if conversation.status == CLOSED:
        raise ConversationClosedError
    if conversation.status != HUMAN_ACTIVE:
        return None

    await _finish_open_handoffs(db, conversation, now)
    changed = (
        await db.execute(
            update(ServiceConversation)
            .where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
                ServiceConversation.status == HUMAN_ACTIVE,
            )
            .values(
                status=AI_ACTIVE,
                assigned_employee_id=None,
                last_activity_at=now,
                updated_at=now,
            )
            .returning(ServiceConversation.id)
        )
    ).scalar_one_or_none()
    if changed is None:
        status = await _current_status(db, tenant_id, conversation_id)
        if status is None:
            return None
        if status == CLOSED:
            raise ConversationClosedError
        return None

    notice = await _write_notice(
        db,
        conversation,
        content=RETURNED_TO_AI_NOTICE,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        now=now,
    )
    return _result(conversation_id, AI_ACTIVE, notice)
