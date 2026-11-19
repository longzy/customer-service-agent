"""坐席关闭会话与转回 AI（plan 3.3.1/3.4）。

- 关闭：`CLAIMED`/`HUMAN_ACTIVE` 可关闭；open 交接单同事务终态化，写“会话已结束”。
- 转回 AI：只允许 `HUMAN_ACTIVE`；会话回 `AI_ACTIVE`、清空 `assigned_employee_id`、
  open 交接单终态化，写“已转回 AI 客服”。客户在同一会话继续对话，历史不丢。
- 错误按**会话实际状态**判定，不看交接单状态（F-07 建议）：会话已关闭 → 409
  `CONVERSATION_CLOSED`；不存在/他人/跨租户/状态不可操作 → None（API 404）。
- 幂等：同一 `Idempotency-Key` 重放返回首次系统消息，系统消息记录动作人
  （`author_id`）；重放按「会话 + 键 + 动作人」命中，他人用同一键得到 404。
  重放返回**动作时**的状态，不读取会话后续演进（避免旧键泄露当前归属/状态）。
  重放先于状态检查：转回会清空 assignment，否则本人的重放会被误判 404。
- 锁顺序：先更新交接单、再条件更新会话，与领取/接管/客户关闭一致，避免交叉等待。
- 交接单 `pending_step` 保持创建时快照，不重写（F-11 D-4；本卡 D-6）。
- 系统消息、重放与交接单终态化复用 `state_changes`，与客户关闭同语义。
- 本模块只 flush，由 API 层统一 commit；失败由调用方回滚。
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.customer_chat import MessageView, view_message
from backend.conversations.customer_close import CLOSED_NOTICE
from backend.conversations.state_changes import (
    close_open_handoffs,
    replay_system_message,
    write_system_message,
)
from backend.conversations.statuses import (
    AI_ACTIVE,
    CLAIMED,
    CLOSED,
    HUMAN_ACTIVE,
    RETURNED_TO_AI_NOTICE,
)
from backend.platform.models import ServiceConversation, ServiceMessage

CLOSABLE_STATUSES = (CLAIMED, HUMAN_ACTIVE)


class ConversationClosedError(Exception):
    """会话已关闭，不再接受坐席写操作；对应 409 `CONVERSATION_CLOSED`。"""


@dataclass(frozen=True)
class AgentStateChange:
    """坐席状态变更回执：系统消息即前端的状态与提示来源。"""

    conversation_id: str
    status: str
    message: MessageView
    journey_id: str
    replayed: bool = False


async def _find_conversation(
    db: AsyncSession, tenant_id: str, conversation_id: str
) -> ServiceConversation | None:
    """同租户会话；不先按归属过滤，本人的重放需要在转回清空 assignment 后仍可命中。"""
    return (
        await db.execute(
            select(ServiceConversation).where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
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


async def _replay_state(
    db: AsyncSession,
    conversation: ServiceConversation,
    idempotency_key: str,
    employee_id: str,
    status: str,
) -> AgentStateChange | None:
    """本人同键重放：只命中本动作人写的系统消息，返回动作时状态。"""
    replay = await replay_system_message(
        db,
        conversation.id,
        idempotency_key,
        author_id=employee_id,
    )
    if replay is None:
        return None
    return _result(conversation.id, status, replay, conversation.journey_id, replayed=True)


def _result(
    conversation_id: str,
    status: str,
    message: ServiceMessage,
    journey_id: str,
    *,
    replayed: bool = False,
) -> AgentStateChange:
    return AgentStateChange(
        conversation_id=conversation_id,
        status=status,
        message=view_message(message),
        journey_id=journey_id,
        replayed=replayed,
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

    replay = await _replay_state(db, conversation, idempotency_key, employee_id, CLOSED)
    if replay is not None:
        return replay

    if conversation.assigned_employee_id != employee_id:
        return None
    if conversation.status == CLOSED:
        raise ConversationClosedError
    if conversation.status not in CLOSABLE_STATUSES:
        return None

    await close_open_handoffs(db, tenant_id, conversation_id, now)
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
        # 读取后被并发关闭/转回：先按同键重放，再按最新状态给 409 或 404。
        replay = await _replay_state(db, conversation, idempotency_key, employee_id, CLOSED)
        if replay is not None:
            return replay
        status = await _current_status(db, tenant_id, conversation_id)
        if status is None:
            return None
        if status == CLOSED:
            raise ConversationClosedError
        return None

    notice = await write_system_message(
        db,
        conversation_id=conversation_id,
        content=CLOSED_NOTICE,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        now=now,
        author_id=employee_id,
    )
    return _result(conversation_id, CLOSED, notice, conversation.journey_id)


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

    replay = await _replay_state(db, conversation, idempotency_key, employee_id, AI_ACTIVE)
    if replay is not None:
        return replay

    if conversation.assigned_employee_id != employee_id:
        return None
    if conversation.status == CLOSED:
        raise ConversationClosedError
    if conversation.status != HUMAN_ACTIVE:
        return None

    await close_open_handoffs(db, tenant_id, conversation_id, now)
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
        replay = await _replay_state(db, conversation, idempotency_key, employee_id, AI_ACTIVE)
        if replay is not None:
            return replay
        status = await _current_status(db, tenant_id, conversation_id)
        if status is None:
            return None
        if status == CLOSED:
            raise ConversationClosedError
        return None

    notice = await write_system_message(
        db,
        conversation_id=conversation_id,
        content=RETURNED_TO_AI_NOTICE,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        now=now,
        author_id=employee_id,
    )
    return _result(conversation_id, AI_ACTIVE, notice, conversation.journey_id)
