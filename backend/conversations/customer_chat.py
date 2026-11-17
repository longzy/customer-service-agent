"""客户消息、AI 回复与模型失败自动转人工。

- 客户消息先落库再调用模型，超时/异常也保留输入。
- 只有 AI_ACTIVE 会话调用模型；排队/人工中只落库，不重复触发 AI。
- 模型 10s 超时或异常：写 AI 事件、建一张 open 交接单、会话转 QUEUED、写系统提示。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_runtime.model import ChatModel, ModelError
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceHandoff,
    ServiceMessage,
)

STATUS_AI_ACTIVE = "AI_ACTIVE"
STATUS_QUEUED = "QUEUED"
STATUS_CLOSED = "CLOSED"
OPEN_HANDOFF_STATUSES = ("QUEUED", "CLAIMED", "ACTIVE")
QUEUE_NOTICE = "排队中，请稍候"


class ConversationClosedError(Exception):
    """已关闭会话不接受新消息。"""


@dataclass(frozen=True)
class MessageView:
    id: int
    author_type: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class ChatResult:
    conversation_id: str
    status: str
    messages: list[MessageView]
    after_id: int


def view_message(row: ServiceMessage) -> MessageView:
    return MessageView(
        id=row.id,
        author_type=row.author_type,
        content=row.content,
        created_at=row.created_at,
    )


async def list_messages(
    db: AsyncSession, conversation_id: str, after_id: int, limit: int = 100
) -> list[MessageView]:
    statement = (
        select(ServiceMessage)
        .where(
            ServiceMessage.conversation_id == conversation_id,
            ServiceMessage.id > after_id,
        )
        .order_by(ServiceMessage.id)
        .limit(limit)
    )
    rows = (await db.execute(statement)).scalars().all()
    return [view_message(row) for row in rows]


async def _record_ai_event(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    status: str,
    confidence: float | None,
    trace_id: str,
    now: datetime,
) -> None:
    db.add(
        ServiceAiEvent(
            id=str(uuid4()),
            conversation_id=conversation.id,
            journey_id=conversation.journey_id,
            event_type="model",
            name="customer_chat",
            status=status,
            confidence=confidence,
            trace_id=trace_id,
            created_at=now,
        )
    )


async def _queue_for_handoff(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    reason: str,
    context: dict[str, object],
    summary: str,
    trace_id: str,
    now: datetime,
) -> ServiceMessage:
    existing = (
        await db.execute(
            select(ServiceHandoff.id).where(
                ServiceHandoff.tenant_id == conversation.tenant_id,
                ServiceHandoff.conversation_id == conversation.id,
                ServiceHandoff.status.in_(OPEN_HANDOFF_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            ServiceHandoff(
                id=str(uuid4()),
                tenant_id=conversation.tenant_id,
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                status=STATUS_QUEUED,
                reason=reason,
                priority="normal",
                summary=summary,
                context=context,
                pending_step="等待坐席接入",
                version=0,
                journey_id=conversation.journey_id,
                created_at=now,
                updated_at=now,
            )
        )
    conversation.status = STATUS_QUEUED
    conversation.updated_at = now
    conversation.last_activity_at = now
    notice = ServiceMessage(
        conversation_id=conversation.id,
        author_type="system",
        author_id=None,
        content=QUEUE_NOTICE,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(notice)
    await db.flush()
    return notice


async def send_customer_message(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_id: str,
    content: str,
    model: ChatModel,
    timeout_seconds: float,
    trace_id: str,
    now: datetime,
) -> ChatResult:
    if conversation.status == STATUS_CLOSED:
        raise ConversationClosedError

    customer_message = ServiceMessage(
        conversation_id=conversation.id,
        author_type="customer",
        author_id=customer_id,
        content=content,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(customer_message)
    await db.flush()
    messages = [view_message(customer_message)]

    if conversation.status != STATUS_AI_ACTIVE:
        conversation.updated_at = now
        conversation.last_activity_at = now
        await db.commit()
        return ChatResult(
            conversation_id=conversation.id,
            status=conversation.status,
            messages=messages,
            after_id=customer_message.id,
        )

    try:
        reply = await asyncio.wait_for(model.respond(content), timeout=timeout_seconds)
    except TimeoutError:
        await _record_ai_event(
            db,
            conversation,
            status="timeout",
            confidence=None,
            trace_id=trace_id,
            now=now,
        )
        notice = await _queue_for_handoff(
            db,
            conversation,
            reason="MODEL_UNAVAILABLE",
            context={"order_count": 0, "trigger": "model_timeout"},
            summary="模型调用超时，已自动转人工。",
            trace_id=trace_id,
            now=now,
        )
        await db.commit()
        return ChatResult(
            conversation_id=conversation.id,
            status=STATUS_QUEUED,
            messages=[messages[0], view_message(notice)],
            after_id=notice.id,
        )
    except ModelError:
        await _record_ai_event(
            db,
            conversation,
            status="error",
            confidence=None,
            trace_id=trace_id,
            now=now,
        )
        notice = await _queue_for_handoff(
            db,
            conversation,
            reason="MODEL_UNAVAILABLE",
            context={"order_count": 0, "trigger": "model_error"},
            summary="模型服务不可用，已自动转人工。",
            trace_id=trace_id,
            now=now,
        )
        await db.commit()
        return ChatResult(
            conversation_id=conversation.id,
            status=STATUS_QUEUED,
            messages=[messages[0], view_message(notice)],
            after_id=notice.id,
        )

    await _record_ai_event(
        db,
        conversation,
        status="ok",
        confidence=reply.confidence,
        trace_id=trace_id,
        now=now,
    )
    ai_message = ServiceMessage(
        conversation_id=conversation.id,
        author_type="ai",
        author_id=None,
        content=reply.reply,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(ai_message)
    conversation.updated_at = now
    conversation.last_activity_at = now
    await db.flush()
    await db.commit()
    return ChatResult(
        conversation_id=conversation.id,
        status=conversation.status,
        messages=[messages[0], view_message(ai_message)],
        after_id=ai_message.id,
    )
