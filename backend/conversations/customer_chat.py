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
from backend.conversations.handoffs import (
    create_handoff,
    decide_model_handoff,
    match_handoff_keyword,
)
from backend.conversations.statuses import (
    AI_ACTIVE,
    CLOSED,
    QUEUED,
)
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
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
    # 审计 seam：新建交接单 / 本条客户消息 / 是否为幂等重放
    handoff_id: str | None = None
    customer_message_id: int | None = None
    replayed: bool = False


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
        customer_message_id=original.id,
        replayed=True,
    )


async def _record_ai_event(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    status: str,
    confidence: float | None,
    trace_id: str,
    now: datetime,
    event_type: str = "model",
    name: str = "customer_chat",
) -> None:
    db.add(
        ServiceAiEvent(
            id=str(uuid4()),
            conversation_id=conversation.id,
            journey_id=conversation.journey_id,
            event_type=event_type,
            name=name,
            status=status,
            confidence=confidence,
            trace_id=trace_id,
            created_at=now,
        )
    )
    await db.flush()


async def _queue_for_handoff(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    reason: str,
    trigger: str,
    summary_hint: str,
    trace_id: str,
    now: datetime,
    matched_keyword: str | None = None,
) -> tuple[ServiceMessage, str | None]:
    conversation.status = QUEUED
    conversation.updated_at = now
    conversation.last_activity_at = now
    handoff, created = await create_handoff(
        db,
        conversation,
        reason=reason,
        trigger=trigger,
        now=now,
        summary_hint=summary_hint,
        matched_keyword=matched_keyword,
    )
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
    return notice, (handoff.id if created else None)


def _queued_result(
    conversation: ServiceConversation,
    customer_message: ServiceMessage,
    notice: ServiceMessage,
    handoff_id: str | None,
) -> ChatResult:
    """所有转人工路径共用的返回结构：客户消息 + 排队系统提示。"""
    return ChatResult(
        conversation_id=conversation.id,
        status=QUEUED,
        messages=[view_message(customer_message), view_message(notice)],
        after_id=notice.id,
        handoff_id=handoff_id,
        customer_message_id=customer_message.id,
    )


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
    notice, handoff_id = await _queue_for_handoff(
        db,
        conversation,
        reason="MODEL_UNAVAILABLE",
        trigger=trigger,
        summary_hint=summary,
        trace_id=trace_id,
        now=now,
    )
    return _queued_result(conversation, customer_message, notice, handoff_id)


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
            customer_message_id=customer_message.id,
        )

    # plan 3.3.4：关键词优先，命中后不调用模型
    keyword = match_handoff_keyword(content)
    if keyword is not None:
        await _record_ai_event(
            db,
            conversation,
            status="matched",
            confidence=None,
            trace_id=trace_id,
            now=now,
            event_type="intent",
            name="handoff_keyword",
        )
        notice, handoff_id = await _queue_for_handoff(
            db,
            conversation,
            reason="CUSTOMER_REQUEST",
            trigger="keyword",
            summary_hint="",
            trace_id=trace_id,
            now=now,
            matched_keyword=keyword,
        )
        return _queued_result(conversation, customer_message, notice, handoff_id)

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
    # plan 3.3.4：低置信/转人工意图/订单/超范围不展示模型回复，直接入队
    decision = decide_model_handoff(
        content=content,
        intent=reply.intent,
        confidence=reply.confidence,
        reply=reply.reply,
    )
    if decision is not None:
        notice, handoff_id = await _queue_for_handoff(
            db,
            conversation,
            reason=decision.reason,
            trigger=decision.trigger,
            summary_hint=decision.summary_hint,
            trace_id=trace_id,
            now=now,
        )
        return _queued_result(conversation, customer_message, notice, handoff_id)

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
        customer_message_id=customer_message.id,
    )
