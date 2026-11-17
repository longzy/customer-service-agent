"""客户消息、AI 回复与模型失败自动转人工。

- 客户消息先落库再调用模型，超时/异常也保留输入。
- 只有 AI_ACTIVE 会话调用模型；排队/人工中只落库，不重复触发 AI。
- 模型 10s 超时或异常：写 AI 事件、建一张 open 交接单、会话转 QUEUED、写系统提示。
- 同一会话内同一幂等键只产生一条客户消息；重放返回原消息及其后非客户消息。
- 本模块只 flush，由 API 层统一 commit。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_runtime.model import ChatModel, ModelError
from backend.conversations.customer_conversations import latest_message_id
from backend.conversations.statuses import (
    AI_ACTIVE,
    CLOSED,
    OPEN_HANDOFF_STATUSES,
    QUEUED,
)
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceHandoff,
    ServiceMessage,
)

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


async def read_customer_messages(
    db: AsyncSession, conversation: ServiceConversation, after_id: int
) -> ChatResult:
    messages = await list_messages(db, conversation.id, after_id)
    if messages:
        latest = messages[-1].id
    else:
        latest = max(after_id, await latest_message_id(db, conversation.id))
    return ChatResult(
        conversation_id=conversation.id,
        status=conversation.status,
        messages=messages,
        after_id=latest,
    )


async def _replay(
    db: AsyncSession, conversation: ServiceConversation, idempotency_key: str
) -> ChatResult | None:
    """同一幂等键重放：返回原客户消息及其后的非客户消息，直到下一条客户消息。"""
    original = (
        await db.execute(
            select(ServiceMessage).where(
                ServiceMessage.conversation_id == conversation.id,
                ServiceMessage.author_type == "customer",
                ServiceMessage.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if original is None:
        return None
    rows = (
        (
            await db.execute(
                select(ServiceMessage)
                .where(
                    ServiceMessage.conversation_id == conversation.id,
                    ServiceMessage.id >= original.id,
                )
                .order_by(ServiceMessage.id)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    messages: list[MessageView] = []
    for row in rows:
        if messages and row.author_type == "customer":
            break
        messages.append(view_message(row))
    after_id = messages[-1].id if messages else original.id
    return ChatResult(
        conversation_id=conversation.id,
        status=conversation.status,
        messages=messages,
        after_id=after_id,
    )


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
                status=QUEUED,
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
    conversation.status = QUEUED
    conversation.updated_at = now
    conversation.last_activity_at = now
    notice = ServiceMessage(
        conversation_id=conversation.id,
        author_type="system",
        author_id=None,
        content=QUEUE_NOTICE,
        idempotency_key=None,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(notice)
    await db.flush()
    return notice


async def _model_failed(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    event_status: str,
    trigger: str,
    summary: str,
    trace_id: str,
    now: datetime,
    customer_message: ServiceMessage,
) -> ChatResult:
    await _record_ai_event(
        db,
        conversation,
        status=event_status,
        confidence=None,
        trace_id=trace_id,
        now=now,
    )
    notice = await _queue_for_handoff(
        db,
        conversation,
        reason="MODEL_UNAVAILABLE",
        context={"order_count": 0, "trigger": trigger},
        summary=summary,
        trace_id=trace_id,
        now=now,
    )
    return ChatResult(
        conversation_id=conversation.id,
        status=QUEUED,
        messages=[view_message(customer_message), view_message(notice)],
        after_id=notice.id,
    )


async def send_customer_message(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_id: str,
    content: str,
    idempotency_key: str,
    model: ChatModel,
    timeout_seconds: float,
    trace_id: str,
    now: datetime,
) -> ChatResult:
    replay = await _replay(db, conversation, idempotency_key)
    if replay is not None:
        return replay
    if conversation.status == CLOSED:
        raise ConversationClosedError

    customer_message = ServiceMessage(
        conversation_id=conversation.id,
        author_type="customer",
        author_id=customer_id,
        content=content,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(customer_message)
    await db.flush()

    if conversation.status != AI_ACTIVE:
        conversation.updated_at = now
        conversation.last_activity_at = now
        await db.flush()
        return ChatResult(
            conversation_id=conversation.id,
            status=conversation.status,
            messages=[view_message(customer_message)],
            after_id=customer_message.id,
        )

    try:
        reply = await asyncio.wait_for(model.respond(content), timeout=timeout_seconds)
    except TimeoutError:
        return await _model_failed(
            db,
            conversation,
            event_status="timeout",
            trigger="model_timeout",
            summary="模型调用超时，已自动转人工。",
            trace_id=trace_id,
            now=now,
            customer_message=customer_message,
        )
    except ModelError:
        return await _model_failed(
            db,
            conversation,
            event_status="error",
            trigger="model_error",
            summary="模型服务不可用，已自动转人工。",
            trace_id=trace_id,
            now=now,
            customer_message=customer_message,
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
        idempotency_key=None,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(ai_message)
    conversation.updated_at = now
    conversation.last_activity_at = now
    await db.flush()
    return ChatResult(
        conversation_id=conversation.id,
        status=conversation.status,
        messages=[view_message(customer_message), view_message(ai_message)],
        after_id=ai_message.id,
    )
