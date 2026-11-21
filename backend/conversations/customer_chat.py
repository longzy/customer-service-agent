"""客户消息、AI 回复与模型失败分级降级。

- 客户消息先落库再调用模型，超时/异常也保留输入。
- 只有 AI_ACTIVE 会话调用模型；排队/人工中只落库，不重复触发 AI。
- 模型 10s 超时或异常（ADR-0011）：单次只写 AI 事件与重试提示，不建单、不改状态；
  同一会话连续 2 次失败才建一张 open 交接单、会话转 QUEUED、写转接提示。
- 同一会话内同一幂等键只产生一条客户消息；重放返回原消息及其后非客户消息。
- 本模块只 flush，由 API 层统一 commit。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_runtime.model import ChatModel, ModelError
from backend.conversations.customer_conversations import latest_message_id
from backend.conversations.handoffs import (
    HANDOFF_CONFIDENCE_THRESHOLD,
    create_handoff,
    decide_model_handoff,
    match_handoff_keyword,
)
from backend.conversations.order_queries import (
    MULTIPLE_ORDERS_REPLY,
    ORDER_QUERY_INTENTS,
    ORDER_QUERY_MULTIPLE,
    ORDER_QUERY_PARTIAL,
    ORDER_QUERY_SINGLE,
    PARTIAL_ORDER_ID_REPLY,
    OrderQueryOutcome,
    extract_order_ids,
    has_non_query_order_intent,
    order_query_kind,
    query_order,
    query_recent_orders,
)
from backend.conversations.statuses import (
    AI_ACTIVE,
    CLOSED,
    QUEUED,
    RETURNED_TO_AI_NOTICE,
)
from backend.identity.customer_sessions import Customer
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceMessage,
)
from backend.tools.gateway import ToolGateway

QUEUE_NOTICE = "排队中，请稍候"
# ADR-0011：单次失败给客户出口；连续失败才兑换成人工队列
RETRY_NOTICE = "AI 暂时不可用，你可以重试，或说“转人工”。"
MODEL_FAILURE_HANDOFF_NOTICE = "AI 暂时不可用，已为你转接人工（排队中）。"
MODEL_FAILURE_STATUSES = frozenset({"timeout", "error"})
MODEL_ERROR_CODES = {"timeout": "MODEL_TIMEOUT", "error": "MODEL_ERROR"}
CONSECUTIVE_FAILURE_LIMIT = 2


class ConversationClosedError(Exception):
    """已关闭会话不接受新消息。"""


@dataclass(frozen=True)
class MessageView:
    id: int
    author_type: str
    content: str
    created_at: datetime
    # AI 订单消息的结构化快照；其他消息为 None。
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ChatResult:
    conversation_id: str
    status: str
    messages: list[MessageView]
    after_id: int
    # 审计 seam：新建交接单 / 本条客户消息 / 是否为幂等重放
    handoff_id: str | None = None
    customer_message_id: int | None = None
    ai_message_id: int | None = None
    replayed: bool = False


def view_message(row: ServiceMessage) -> MessageView:
    return MessageView(
        id=row.id,
        author_type=row.author_type,
        content=row.content,
        created_at=row.created_at,
        payload=row.payload,
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


async def _order_result(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_message: ServiceMessage,
    outcome: OrderQueryOutcome,
    trace_id: str,
    now: datetime,
) -> ChatResult:
    """订单查询结果落地：成功/查无/失败都只回消息，不建单、不改状态。"""
    await _record_ai_event(
        db,
        conversation,
        status=outcome.status,
        confidence=None,
        trace_id=trace_id,
        now=now,
        event_type="order_query",
        name=outcome.tool,
    )
    ai_message = ServiceMessage(
        conversation_id=conversation.id,
        author_type="ai",
        author_id=None,
        content=outcome.reply,
        payload={"orders": outcome.orders},
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
        ai_message_id=ai_message.id,
    )


async def _order_clarification(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_message: ServiceMessage,
    content: str,
    trace_id: str,
    now: datetime,
) -> ChatResult:
    """多单/半截澄清：不查 OMS、不写订单事件、不带订单快照（AC-52）。"""
    ai_message = ServiceMessage(
        conversation_id=conversation.id,
        author_type="ai",
        author_id=None,
        content=content,
        payload=None,
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
        ai_message_id=ai_message.id,
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
    prompt_version: str | None = None,
    prompt_hash: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    first_token_latency_ms: int | None = None,
    retry_count: int = 0,
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
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            first_token_latency_ms=first_token_latency_ms,
            retry_count=retry_count,
            trace_id=trace_id,
            created_at=now,
        )
    )
    await db.flush()


async def _append_notice(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    content: str,
    trace_id: str,
    now: datetime,
) -> ServiceMessage:
    """写一条系统提示并推进会话活跃时间；单次失败与转人工共用。"""
    notice = ServiceMessage(
        conversation_id=conversation.id,
        author_type="system",
        author_id=None,
        content=content,
        idempotency_key=None,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(notice)
    conversation.updated_at = now
    conversation.last_activity_at = now
    await db.flush()
    return notice


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
    notice_text: str = QUEUE_NOTICE,
    failure_count: int | None = None,
    last_error: str | None = None,
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
        failure_count=failure_count,
        last_error=last_error,
    )
    notice = await _append_notice(
        db,
        conversation,
        content=notice_text,
        trace_id=trace_id,
        now=now,
    )
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


async def _consecutive_model_failures(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_message: ServiceMessage,
) -> int:
    """最近两条模型事件都失败才算连续；成功回复的 `ok` 事件会打断计数。

    “连续”按同一会话相邻两条客户消息判定：较旧的失败事件必须不早于
    当前消息之前那条客户消息，避免把人工转回 AI 前的失败算进来。
    当前失败事件已由 `_record_ai_event` flush，是最近一条 model 事件。
    """
    rows = list(
        (
            await db.execute(
                select(ServiceAiEvent)
                .where(
                    ServiceAiEvent.conversation_id == conversation.id,
                    ServiceAiEvent.event_type == "model",
                )
                .order_by(ServiceAiEvent.created_at.desc(), ServiceAiEvent.id.desc())
                .limit(CONSECUTIVE_FAILURE_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) < CONSECUTIVE_FAILURE_LIMIT:
        return 1
    if any(row.status not in MODEL_FAILURE_STATUSES for row in rows):
        return 1
    previous = (
        await db.execute(
            select(ServiceMessage.id, ServiceMessage.created_at)
            .where(
                ServiceMessage.conversation_id == conversation.id,
                ServiceMessage.author_type == "customer",
                ServiceMessage.id < customer_message.id,
            )
            .order_by(ServiceMessage.id.desc())
            .limit(1)
        )
    ).first()
    if previous is None:
        return 1
    # 人工转回 AI 是新的起点：上一条客户消息之后出现“已转回 AI 客服”时，
    # 转回前的失败不计入本次连续失败。
    returned = (
        await db.execute(
            select(ServiceMessage.id)
            .where(
                ServiceMessage.conversation_id == conversation.id,
                ServiceMessage.author_type == "system",
                ServiceMessage.content == RETURNED_TO_AI_NOTICE,
                ServiceMessage.id > previous.id,
                ServiceMessage.id < customer_message.id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if returned is not None or rows[1].created_at < previous.created_at:
        return 1
    return CONSECUTIVE_FAILURE_LIMIT


async def _model_failed(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    event_status: str,
    trigger: str,
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
    failures = await _consecutive_model_failures(
        db, conversation, customer_message=customer_message
    )
    if failures < CONSECUTIVE_FAILURE_LIMIT:
        notice = await _append_notice(
            db,
            conversation,
            content=RETRY_NOTICE,
            trace_id=trace_id,
            now=now,
        )
        return ChatResult(
            conversation_id=conversation.id,
            status=conversation.status,
            messages=[view_message(customer_message), view_message(notice)],
            after_id=notice.id,
            customer_message_id=customer_message.id,
        )

    error_code = MODEL_ERROR_CODES[event_status]
    notice, handoff_id = await _queue_for_handoff(
        db,
        conversation,
        reason="MODEL_UNAVAILABLE",
        trigger=trigger,
        summary_hint=f"模型连续 {failures} 次失败（最后一次：{error_code}），已自动转人工",
        trace_id=trace_id,
        now=now,
        notice_text=MODEL_FAILURE_HANDOFF_NOTICE,
        failure_count=failures,
        last_error=error_code,
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
    customer: Customer,
    order_gateway: ToolGateway | None,
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

    # plan 3.3.4：关键词优先；订单分支先做确定性护栏，再决定是否调模型。
    # 取消/退款等"对订单做别的操作"保持 001 的转人工路径，不能被查询分支截走。
    order_kind = order_query_kind(content)
    if order_kind == ORDER_QUERY_MULTIPLE:
        return await _order_clarification(
            db,
            conversation,
            customer_message=customer_message,
            content=MULTIPLE_ORDERS_REPLY,
            trace_id=trace_id,
            now=now,
        )
    if order_kind == ORDER_QUERY_PARTIAL:
        return await _order_clarification(
            db,
            conversation,
            customer_message=customer_message,
            content=PARTIAL_ORDER_ID_REPLY,
            trace_id=trace_id,
            now=now,
        )
    if order_kind == ORDER_QUERY_SINGLE:
        [order_id] = extract_order_ids(content)
        outcome = await query_order(order_gateway, customer, order_id, trace_id)
        return await _order_result(
            db,
            conversation,
            customer_message=customer_message,
            outcome=outcome,
            trace_id=trace_id,
            now=now,
        )

    try:
        reply = await asyncio.wait_for(model.respond(content), timeout=timeout_seconds)
    except TimeoutError:
        return await _model_failed(
            db,
            conversation,
            event_status="timeout",
            trigger="model_timeout",
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
        prompt_version=reply.prompt_version,
        prompt_hash=reply.prompt_hash,
        model=reply.model,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        first_token_latency_ms=reply.first_token_latency_ms,
        retry_count=reply.retry_count,
    )
    # 无订单号的订单意图（plan 3.1）：模型只输出意图，查询仍由服务端确定性执行。
    # 低置信保持 001 的转人工护栏；取消/退款等操作词不允许被订单意图截走。
    normalized_intent = reply.intent.strip().upper()
    if (
        normalized_intent in ORDER_QUERY_INTENTS
        and reply.confidence >= HANDOFF_CONFIDENCE_THRESHOLD
        and not has_non_query_order_intent(content)
    ):
        outcome = await query_recent_orders(order_gateway, customer, trace_id)
        return await _order_result(
            db,
            conversation,
            customer_message=customer_message,
            outcome=outcome,
            trace_id=trace_id,
            now=now,
        )

    # plan 3.3.4：低置信/转人工意图/超范围不展示模型回复，直接入队
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
        ai_message_id=ai_message.id,
    )
