"""客户消息、AI 回复与失败分级降级。

- 客户消息先落库再调用模型，超时/异常也保留输入。
- 只有 AI_ACTIVE 会话调用模型；排队/人工中只落库，不重复触发 AI。
- 模型 10s 超时或异常（ADR-0011）：单次只写 AI 事件与重试提示，不建单、不改状态；
  同一会话连续 2 次失败才建一张 open 交接单、会话转 QUEUED、写转接提示。
- 订单查询失败（F-27）：单次只提示重试且不建单；同一会话连续 2 次失败才转人工。
  订单失败与模型失败按事件类型各自计数，互不并入。
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
from backend.conversations.cancel_intents import has_cancel_intent, match_confirm_cancel_phrase
from backend.conversations.customer_cancellations import (
    CancellationStateConflict,
    CancellationTaskNotFound,
    confirm_cancellation,
    latest_awaiting_confirmation,
    request_cancellation,
)
from backend.conversations.customer_conversations import latest_message_id
from backend.conversations.handoffs import (
    HANDOFF_CONFIDENCE_THRESHOLD,
    ORDER_CONTEXT_EMPTY,
    ORDER_CONTEXT_FAILED,
    ORDER_CONTEXT_OK,
    ORDER_CONTEXT_UNKNOWN,
    OrderContextStatus,
    create_handoff,
    decide_model_handoff,
    match_handoff_keyword,
    match_out_of_scope_term,
)
from backend.conversations.order_queries import (
    MULTIPLE_ORDERS_REPLY,
    NOT_FOUND_REPLY,
    ORDER_FAILURE_HANDOFF_NOTICE,
    ORDER_FAILURE_STATUSES,
    ORDER_QUERY_INTENTS,
    ORDER_QUERY_MULTIPLE,
    ORDER_QUERY_NONE,
    ORDER_QUERY_PARTIAL,
    ORDER_QUERY_SINGLE,
    PARTIAL_ORDER_ID_REPLY,
    UNAVAILABLE_REPLY,
    OrderQueryAudit,
    OrderQueryOutcome,
    build_order_reply,
    build_recent_orders_reply,
    extract_order_ids,
    has_non_query_order_intent,
    order_query_audit,
    order_query_kind,
    query_order,
    query_recent_orders,
    wants_recent_orders,
)
from backend.conversations.statuses import (
    AI_ACTIVE,
    CLOSED,
    QUEUED,
    RETURNED_TO_AI_NOTICE,
)
from backend.domain.cancellation import CancellationState, render_result
from backend.identity.customer_sessions import Customer
from backend.platform.http import utc_text
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceMessage,
)
from backend.tools.gateway import GatewayError, ToolGateway
from backend.workflows.cancel import CancellationTask

QUEUE_NOTICE = "排队中，请稍候"
# ADR-0011：单次失败给客户出口；连续失败才兑换成人工队列
RETRY_NOTICE = "AI 暂时不可用，你可以重试，或说“转人工”。"
MODEL_FAILURE_HANDOFF_NOTICE = "AI 暂时不可用，已为你转接人工（排队中）。"
MODEL_FAILURE_STATUSES = frozenset({"timeout", "error"})
MODEL_ERROR_CODES = {"timeout": "MODEL_TIMEOUT", "error": "MODEL_ERROR"}
CONSECUTIVE_FAILURE_LIMIT = 2
# F-28：转人工时回看本会话最近多少条带 payload 的 AI 消息，找最近的订单快照。
HANDOFF_SNAPSHOT_LOOKBACK = 20
# F-27：订单失败与模型失败是两套独立计数，交接单用同一组字段表达。
ORDER_QUERY_FAILURE_REASON = "ORDER_QUERY_FAILURE"
ORDER_QUERY_FAILURE_TRIGGER = "order_query_failure"
ORDER_QUERY_ERROR_FALLBACK = "ORDER_QUERY_FAILED"

# F-32：取消分支的确定性文案。卡片数据在消息 payload 里，文案只做引导；
# “尚未提交”是 AC-60/AC-63 的产品承诺，任何改字都要同步前端断言。
CANCEL_CONFIRM_NOTICE = (
    "尚未提交。回复「确认取消」提交，或回复「不取消」放弃；也可以到「我的订单」确认。"
)
CANCEL_CANDIDATES_REPLY = (
    "你名下有多个最近订单，我不能替你选。请点要取消的订单卡片上的「取消订单」，或回复订单号。"
)
CANCEL_NO_PENDING_REPLY = "当前没有待确认的取消。可以说「取消订单」，或到「我的订单」发起。"
CANCEL_CONFLICT_REPLY = "取消状态刚刚变化，请稍后在「我的订单」查看。"


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
    # 本次消息触发的真实订单查询；HTTP 层据此写 `order.queried`。
    order_query: OrderQueryAudit | None = None


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
    customer: Customer,
    outcome: OrderQueryOutcome,
    trace_id: str,
    now: datetime,
    preface: str | None = None,
) -> ChatResult:
    """订单查询结果落地：成功/查无只回消息；失败按 F-27 分级。

    - 单次超时/异常/非法响应：只写 AI 提示，不建单、不改状态；
    - 同会话连续 2 次失败：走现有转人工路径，交接单带 `failure_count`/`last_error`。
    """
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
    if outcome.status in ORDER_FAILURE_STATUSES:
        failures = await _consecutive_order_failures(db, conversation)
        if failures >= CONSECUTIVE_FAILURE_LIMIT:
            last_error = outcome.error_code or ORDER_QUERY_ERROR_FALLBACK
            notice, handoff_id, _ = await _queue_for_handoff(
                db,
                conversation,
                reason=ORDER_QUERY_FAILURE_REASON,
                trigger=ORDER_QUERY_FAILURE_TRIGGER,
                summary_hint=(
                    f"订单查询连续 {failures} 次失败（最后一次：{last_error}），已自动转人工"
                ),
                customer=customer,
                trace_id=trace_id,
                now=now,
                notice_text=ORDER_FAILURE_HANDOFF_NOTICE,
                failure_count=failures,
                last_error=last_error,
                # 已知 OMS 不可用：不再补查，订单上下文明确标记为不可用。
                orders=[],
                order_context_status=ORDER_CONTEXT_FAILED,
            )
            return _queued_result(
                conversation,
                customer_message,
                notice,
                handoff_id,
                order_query=order_query_audit(outcome),
            )
    # 候选只在查询成功时拼接引导；失败/空结果用独立文案，避免“先列出…：不可用”。
    content = (
        f"{preface}\n{outcome.reply}"
        if preface is not None and outcome.status == "ok"
        else outcome.reply
    )
    ai_message = ServiceMessage(
        conversation_id=conversation.id,
        author_type="ai",
        author_id=None,
        content=content,
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
        order_query=order_query_audit(outcome),
    )


async def _recent_ai_events(
    db: AsyncSession, conversation: ServiceConversation, event_type: str
) -> list[ServiceAiEvent]:
    """按时间倒序取最近 `CONSECUTIVE_FAILURE_LIMIT` 条指定类型事件。

    模型失败与订单失败共用同一查询，只有失败状态集合与"连续"边界不同。
    """
    return list(
        (
            await db.execute(
                select(ServiceAiEvent)
                .where(
                    ServiceAiEvent.conversation_id == conversation.id,
                    ServiceAiEvent.event_type == event_type,
                )
                .order_by(ServiceAiEvent.created_at.desc(), ServiceAiEvent.id.desc())
                .limit(CONSECUTIVE_FAILURE_LIMIT)
            )
        )
        .scalars()
        .all()
    )


async def _consecutive_order_failures(db: AsyncSession, conversation: ServiceConversation) -> int:
    """同会话最近两次订单查询都失败才算连续；有效结果与转回 AI 会清零。

    与 `_consecutive_model_failures` 的差异：订单失败只按 `order_query` 事件
    序列判定，中间的普通聊天不写订单事件、不打断；`ok`/`not_found` 是有效
    查询结果，任何一个都让计数回到 1。"已转回 AI 客服"系统消息出现时重新
    计数（与 F-24 一致，转回是新的起点）。
    """
    rows = await _recent_ai_events(db, conversation, "order_query")
    if len(rows) < CONSECUTIVE_FAILURE_LIMIT:
        return 1
    if any(row.status not in ORDER_FAILURE_STATUSES for row in rows):
        return 1
    returned = (
        await db.execute(
            select(ServiceMessage.id)
            .where(
                ServiceMessage.conversation_id == conversation.id,
                ServiceMessage.author_type == "system",
                ServiceMessage.content == RETURNED_TO_AI_NOTICE,
                ServiceMessage.created_at >= rows[1].created_at,
                ServiceMessage.created_at <= rows[0].created_at,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if returned is not None:
        return 1
    return CONSECUTIVE_FAILURE_LIMIT


async def _recent_orders_result(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_message: ServiceMessage,
    customer: Customer,
    trace_id: str,
    now: datetime,
    gateway: ToolGateway | None,
    preface: str | None = None,
) -> ChatResult:
    """查一次最近订单并落地；多单/半截/确定性入口/模型意图共用。"""
    outcome = await query_recent_orders(gateway, customer, trace_id)
    return await _order_result(
        db,
        conversation,
        customer_message=customer_message,
        customer=customer,
        outcome=outcome,
        trace_id=trace_id,
        now=now,
        preface=preface,
    )


def _cancellation_payload(task: CancellationTask, now: datetime) -> dict[str, Any]:
    """聊天确认/结果卡片的最小任务视图；文案仍来自 `render_result` 唯一出口。"""
    copy = render_result(task.state, task.reason_code)
    return {
        "state": task.state.value,
        "status_text": copy.state_text,
        "next_step": copy.next_step,
        "expires_at": utc_text(task.expires_at),
        "can_confirm": task.state is CancellationState.AWAITING_CONFIRMATION
        and now < task.expires_at,
    }


async def _cancel_message(
    db: AsyncSession,
    conversation: ServiceConversation,
    customer_message: ServiceMessage,
    *,
    content: str,
    orders: list[dict[str, Any]],
    cancellation: dict[str, Any] | None,
    trace_id: str,
    now: datetime,
    order_query: OrderQueryAudit | None = None,
) -> ChatResult:
    """取消分支统一落一条 AI 消息：正文引导 + payload 订单/任务快照。"""
    payload: dict[str, Any] = {"orders": orders}
    if cancellation is not None:
        payload["cancellation"] = cancellation
    ai_message = ServiceMessage(
        conversation_id=conversation.id,
        author_type="ai",
        author_id=None,
        content=content,
        payload=payload,
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
        order_query=order_query,
    )


async def _cancel_candidates(
    db: AsyncSession,
    conversation: ServiceConversation,
    customer_message: ServiceMessage,
    *,
    orders: list[dict[str, Any]],
    preface: str,
    trace_id: str,
    now: datetime,
    order_query: OrderQueryAudit | None = None,
) -> ChatResult:
    """列候选：正文与卡片都只展示白名单摘要，不替客户选单。"""
    return await _cancel_message(
        db,
        conversation,
        customer_message,
        content=f"{preface}\n{build_recent_orders_reply(orders)}",
        orders=orders,
        cancellation=None,
        trace_id=trace_id,
        now=now,
        order_query=order_query,
    )


async def _cancel_result(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_message: ServiceMessage,
    customer: Customer,
    order_ids: list[str],
    trace_id: str,
    now: datetime,
    order_gateway: ToolGateway | None,
    cancel_gateway: ToolGateway | None,
    confirm_timeout_minutes: int,
) -> ChatResult:
    """取消分支：确定性定位订单，再发起/复用任务并写确认卡片（AC-63）。

    定位顺序：显式订单号 > 会话内最近一次成功查询恰好一笔 > 最近订单列表。
    多单只列候选，不替客户选；快照只用于定位，摘要统一以 OMS 最新结果为准。
    """
    order_id: str | None = None
    summary: dict[str, Any] | None = None
    audit: OrderQueryAudit | None = None

    if len(order_ids) > 1:
        # 客户自己给了多个订单号：同样不替客户选。
        outcome = await query_recent_orders(order_gateway, customer, trace_id)
        if outcome.status in ORDER_FAILURE_STATUSES:
            return await _order_result(
                db,
                conversation,
                customer_message=customer_message,
                customer=customer,
                outcome=outcome,
                trace_id=trace_id,
                now=now,
            )
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
        audit = order_query_audit(outcome)
        if not outcome.orders:
            return await _cancel_message(
                db,
                conversation,
                customer_message,
                content=outcome.reply,
                orders=[],
                cancellation=None,
                trace_id=trace_id,
                now=now,
                order_query=audit,
            )
        return await _cancel_candidates(
            db,
            conversation,
            customer_message,
            orders=outcome.orders,
            preface=MULTIPLE_ORDERS_REPLY,
            trace_id=trace_id,
            now=now,
            order_query=audit,
        )

    if order_ids:
        order_id = order_ids[0]
    else:
        snapshot = await _latest_order_snapshot(db, conversation)
        if snapshot is not None and len(snapshot) == 1:
            order_id = str(snapshot[0].get("order_id", "")) or None
        elif snapshot is not None:
            return await _cancel_candidates(
                db,
                conversation,
                customer_message,
                orders=snapshot,
                preface=CANCEL_CANDIDATES_REPLY,
                trace_id=trace_id,
                now=now,
            )
        if order_id is None:
            outcome = await query_recent_orders(order_gateway, customer, trace_id)
            if outcome.status in ORDER_FAILURE_STATUSES:
                return await _order_result(
                    db,
                    conversation,
                    customer_message=customer_message,
                    customer=customer,
                    outcome=outcome,
                    trace_id=trace_id,
                    now=now,
                )
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
            audit = order_query_audit(outcome)
            if not outcome.orders:
                return await _cancel_message(
                    db,
                    conversation,
                    customer_message,
                    content=outcome.reply,
                    orders=[],
                    cancellation=None,
                    trace_id=trace_id,
                    now=now,
                    order_query=audit,
                )
            if len(outcome.orders) > 1:
                return await _cancel_candidates(
                    db,
                    conversation,
                    customer_message,
                    orders=outcome.orders,
                    preface=CANCEL_CANDIDATES_REPLY,
                    trace_id=trace_id,
                    now=now,
                    order_query=audit,
                )
            summary = outcome.orders[0]
            order_id = str(summary["order_id"])

    if summary is None and order_id is not None:
        outcome = await query_order(order_gateway, customer, order_id, trace_id)
        if outcome.status in ORDER_FAILURE_STATUSES:
            return await _order_result(
                db,
                conversation,
                customer_message=customer_message,
                customer=customer,
                outcome=outcome,
                trace_id=trace_id,
                now=now,
            )
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
        audit = order_query_audit(outcome)
        if not outcome.orders:
            return await _cancel_message(
                db,
                conversation,
                customer_message,
                content=outcome.reply,
                orders=[],
                cancellation=None,
                trace_id=trace_id,
                now=now,
                order_query=audit,
            )
        summary = outcome.orders[0]

    if summary is None or order_id is None:
        # 定位路径已在上方穷尽；保留出口避免把 None 传给网关。
        return await _cancel_message(
            db,
            conversation,
            customer_message,
            content=CANCEL_NO_PENDING_REPLY,
            orders=[],
            cancellation=None,
            trace_id=trace_id,
            now=now,
        )

    try:
        task = await request_cancellation(
            db,
            cancel_gateway,
            customer,
            order_id,
            trace_id=trace_id,
            now=now,
            confirm_timeout_minutes=confirm_timeout_minutes,
            conversation_id=conversation.id,
        )
    except GatewayError as error:
        content = NOT_FOUND_REPLY if error.status_code == 404 else UNAVAILABLE_REPLY
        return await _cancel_message(
            db,
            conversation,
            customer_message,
            content=content,
            orders=[summary],
            cancellation=None,
            trace_id=trace_id,
            now=now,
            order_query=audit,
        )

    if task.state is CancellationState.AWAITING_CONFIRMATION:
        content = f"{build_order_reply(summary)}\n{CANCEL_CONFIRM_NOTICE}"
    else:
        content = render_result(task.state, task.reason_code).reply
    return await _cancel_message(
        db,
        conversation,
        customer_message,
        content=content,
        orders=[summary],
        cancellation=_cancellation_payload(task, now),
        trace_id=trace_id,
        now=now,
        order_query=audit,
    )


async def _confirm_phrase_result(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer_message: ServiceMessage,
    customer: Customer,
    trace_id: str,
    now: datetime,
    cancel_gateway: ToolGateway | None,
    confirm_timeout_minutes: int,
) -> ChatResult:
    """固定短语确认：命中客户最近等待确认任务后走同一确认服务（PHRASE）。"""
    snapshot = await latest_awaiting_confirmation(db, customer)
    if snapshot is None:
        return await _cancel_message(
            db,
            conversation,
            customer_message,
            content=CANCEL_NO_PENDING_REPLY,
            orders=[],
            cancellation=None,
            trace_id=trace_id,
            now=now,
        )
    try:
        task = await confirm_cancellation(
            db,
            cancel_gateway,
            customer,
            snapshot.id,
            now=now,
            confirm_timeout_minutes=confirm_timeout_minutes,
            confirmation_source="PHRASE",
        )
    except (CancellationTaskNotFound, CancellationStateConflict):
        # 并发下任务可能已被推进或消失：只提示，不猜测新状态、不重复提交。
        return await _cancel_message(
            db,
            conversation,
            customer_message,
            content=CANCEL_CONFLICT_REPLY,
            orders=[],
            cancellation=None,
            trace_id=trace_id,
            now=now,
        )
    return await _cancel_message(
        db,
        conversation,
        customer_message,
        content=render_result(task.state, task.reason_code).reply,
        orders=[],
        cancellation=_cancellation_payload(task, now),
        trace_id=trace_id,
        now=now,
    )


async def _latest_order_snapshot(
    db: AsyncSession, conversation: ServiceConversation
) -> list[dict[str, Any]] | None:
    """本会话最近一条非空订单快照；转人工时复用，不重新查 OMS（plan 3.1）。"""
    rows = (
        (
            await db.execute(
                select(ServiceMessage.payload)
                .where(
                    ServiceMessage.conversation_id == conversation.id,
                    ServiceMessage.author_type == "ai",
                    ServiceMessage.payload.is_not(None),
                )
                .order_by(ServiceMessage.id.desc())
                .limit(HANDOFF_SNAPSHOT_LOOKBACK)
            )
        )
        .scalars()
        .all()
    )
    for payload in rows:
        if not isinstance(payload, dict):
            continue
        orders = payload.get("orders")
        if isinstance(orders, list) and orders and all(isinstance(order, dict) for order in orders):
            return orders
    return None


async def _handoff_order_context(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    customer: Customer,
    order_gateway: ToolGateway | None,
    trace_id: str,
    now: datetime,
    allow_lookup: bool,
) -> tuple[list[dict[str, Any]], OrderContextStatus, OrderQueryAudit | None]:
    """转人工时的订单上下文：优先复用快照，客户主动要人时才补查一次。

    返回 `(orders, order_context_status, order_query)`：有订单 `ok`、查无/未绑定
    `empty`、补查失败 `failed`、未发起查询 `unknown`（AC-55/AC-56）。补查失败
    不抛、不阻塞转人工（plan 3.1）；补查是真实查询，需带审计事实（AC-57）。
    """
    snapshot = await _latest_order_snapshot(db, conversation)
    if snapshot is not None:
        return snapshot, ORDER_CONTEXT_OK, None
    if not allow_lookup:
        # AI 主动转人工且会话内没有已查快照：没有发起查询，不能断言“无订单”。
        return [], ORDER_CONTEXT_UNKNOWN, None
    outcome = await query_recent_orders(order_gateway, customer, trace_id)
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
    audit = order_query_audit(outcome)
    if outcome.status == "ok" and outcome.orders:
        return outcome.orders, ORDER_CONTEXT_OK, audit
    if outcome.status in ORDER_FAILURE_STATUSES:
        return [], ORDER_CONTEXT_FAILED, audit
    return [], ORDER_CONTEXT_EMPTY, audit


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
    customer: Customer,
    order_gateway: ToolGateway | None = None,
    allow_order_lookup: bool = False,
    orders: list[dict[str, Any]] | None = None,
    order_context_status: OrderContextStatus | None = None,
    matched_keyword: str | None = None,
    notice_text: str = QUEUE_NOTICE,
    failure_count: int | None = None,
    last_error: str | None = None,
) -> tuple[ServiceMessage, str | None, OrderQueryAudit | None]:
    """转人工统一入口：先落订单上下文，再改状态、建单、写排队提示。

    `orders is None` 表示还没算过上下文：复用会话内快照，客户主动要人
    （`allow_order_lookup=True`）才补查一次最近订单；显式传 `orders` 的
    路径（如订单连续失败）直接使用给定快照，不再打 OMS。
    """
    audit: OrderQueryAudit | None = None
    if orders is None:
        orders, status, audit = await _handoff_order_context(
            db,
            conversation,
            customer=customer,
            order_gateway=order_gateway,
            trace_id=trace_id,
            now=now,
            allow_lookup=allow_order_lookup,
        )
    else:
        status = order_context_status or (ORDER_CONTEXT_OK if orders else ORDER_CONTEXT_EMPTY)
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
        orders=orders,
        order_context_status=status,
    )
    notice = await _append_notice(
        db,
        conversation,
        content=notice_text,
        trace_id=trace_id,
        now=now,
    )
    return notice, (handoff.id if created else None), audit


def _queued_result(
    conversation: ServiceConversation,
    customer_message: ServiceMessage,
    notice: ServiceMessage,
    handoff_id: str | None,
    *,
    order_query: OrderQueryAudit | None = None,
) -> ChatResult:
    """所有转人工路径共用的返回结构：客户消息 + 排队系统提示。"""
    return ChatResult(
        conversation_id=conversation.id,
        status=QUEUED,
        messages=[view_message(customer_message), view_message(notice)],
        after_id=notice.id,
        handoff_id=handoff_id,
        customer_message_id=customer_message.id,
        order_query=order_query,
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
    rows = await _recent_ai_events(db, conversation, "model")
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
    customer: Customer,
    order_gateway: ToolGateway | None,
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
    notice, handoff_id, _ = await _queue_for_handoff(
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
        customer=customer,
        order_gateway=order_gateway,
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
    cancel_gateway: ToolGateway | None,
    confirm_timeout_minutes: int,
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
        notice, handoff_id, order_query = await _queue_for_handoff(
            db,
            conversation,
            reason="CUSTOMER_REQUEST",
            trigger="keyword",
            summary_hint="",
            trace_id=trace_id,
            now=now,
            matched_keyword=keyword,
            customer=customer,
            order_gateway=order_gateway,
            # 客户主动要人：无快照时补查一次最近订单（plan 3.1）。
            allow_order_lookup=True,
        )
        return _queued_result(
            conversation,
            customer_message,
            notice,
            handoff_id,
            order_query=order_query,
        )

    # F-32：固定短语与取消意图在模型之前确定性分流；退款/退货等仍交回 001 路径。
    if match_confirm_cancel_phrase(content) is not None:
        await _record_ai_event(
            db,
            conversation,
            status="matched",
            confidence=None,
            trace_id=trace_id,
            now=now,
            event_type="intent",
            name="cancel_phrase",
        )
        return await _confirm_phrase_result(
            db,
            conversation,
            customer_message=customer_message,
            customer=customer,
            trace_id=trace_id,
            now=now,
            cancel_gateway=cancel_gateway,
            confirm_timeout_minutes=confirm_timeout_minutes,
        )
    if has_cancel_intent(content):
        await _record_ai_event(
            db,
            conversation,
            status="matched",
            confidence=None,
            trace_id=trace_id,
            now=now,
            event_type="intent",
            name="cancel_intent",
        )
        return await _cancel_result(
            db,
            conversation,
            customer_message=customer_message,
            customer=customer,
            order_ids=extract_order_ids(content),
            trace_id=trace_id,
            now=now,
            order_gateway=order_gateway,
            cancel_gateway=cancel_gateway,
            confirm_timeout_minutes=confirm_timeout_minutes,
        )

    # plan 3.3.4：关键词优先；订单分支先做确定性护栏，再决定是否调模型。
    # 取消/退款等操作词由 `order_query_kind` 排除；物流/快递/退款等确定性
    # 超范围词（001 AC-32）让整条订单分支让路，不能被订单意图截走。
    overscope = match_out_of_scope_term(content)
    order_kind = ORDER_QUERY_NONE if overscope is not None else order_query_kind(content)
    if order_kind == ORDER_QUERY_MULTIPLE:
        return await _recent_orders_result(
            db,
            conversation,
            customer_message=customer_message,
            customer=customer,
            trace_id=trace_id,
            now=now,
            gateway=order_gateway,
            preface=MULTIPLE_ORDERS_REPLY,
        )
    if order_kind == ORDER_QUERY_PARTIAL:
        return await _recent_orders_result(
            db,
            conversation,
            customer_message=customer_message,
            customer=customer,
            trace_id=trace_id,
            now=now,
            gateway=order_gateway,
            preface=PARTIAL_ORDER_ID_REPLY,
        )
    if order_kind == ORDER_QUERY_SINGLE:
        [order_id] = extract_order_ids(content)
        outcome = await query_order(order_gateway, customer, order_id, trace_id)
        return await _order_result(
            db,
            conversation,
            customer_message=customer_message,
            customer=customer,
            outcome=outcome,
            trace_id=trace_id,
            now=now,
        )
    # 确定性列表入口：快捷按钮/“我的订单”等不依赖模型意图，少一次模型调用。
    if overscope is None and wants_recent_orders(content):
        return await _recent_orders_result(
            db,
            conversation,
            customer_message=customer_message,
            customer=customer,
            trace_id=trace_id,
            now=now,
            gateway=order_gateway,
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
            customer=customer,
            order_gateway=order_gateway,
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
            customer=customer,
            order_gateway=order_gateway,
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
        and overscope is None
        and not has_non_query_order_intent(content)
    ):
        return await _recent_orders_result(
            db,
            conversation,
            customer_message=customer_message,
            customer=customer,
            trace_id=trace_id,
            now=now,
            gateway=order_gateway,
        )

    # plan 3.3.4：低置信/转人工意图/超范围不展示模型回复，直接入队
    decision = decide_model_handoff(
        content=content,
        intent=reply.intent,
        confidence=reply.confidence,
        reply=reply.reply,
    )
    if decision is not None:
        notice, handoff_id, _ = await _queue_for_handoff(
            db,
            conversation,
            reason=decision.reason,
            trigger=decision.trigger,
            summary_hint=decision.summary_hint,
            trace_id=trace_id,
            now=now,
            customer=customer,
            order_gateway=order_gateway,
            # AI 主动转人工：只复用会话内已有快照，不额外打 OMS（D-2）。
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
