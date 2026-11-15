"""人工转接：组装上下文并落库，供后续坐席系统消费。"""

import re
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth import Identity
from services.api.models import CancellationRequest, Conversation, Handoff, Message

ORDER_PATTERN = re.compile(r"ORD-\d{4,12}", re.IGNORECASE)

PENDING_STEP = {
    "COLLECTING": "正在确认订单信息",
    "AWAITING_CONFIRMATION": "等待用户确认取消",
    "SUBMITTING": "核实取消受理结果",
    "SUBMIT_UNKNOWN": "核实取消受理结果",
    "MANUAL_REVIEW": "等待人工处理",
}


async def create_handoff(
    session: AsyncSession,
    identity: Identity,
    conversation_id: str | None,
    trace_id: str,
) -> Handoff:
    conversation = None
    if conversation_id is not None:
        conversation = await session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == identity.tenant_id,
                Conversation.user_id == identity.user_id,
            )
        )
        if conversation is None:
            raise LookupError("会话不存在")
    else:
        conversation = Conversation(
            id=str(uuid4()), tenant_id=identity.tenant_id, user_id=identity.user_id
        )
        session.add(conversation)
        await session.flush()
        conversation_id = conversation.id

    messages = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    ).scalars()
    rows = list(messages)
    summary = "\n".join(f"{row.role}: {row.content}" for row in rows[-20:])

    task = await session.scalar(
        select(CancellationRequest)
        .where(CancellationRequest.conversation_id == conversation_id)
        .order_by(CancellationRequest.created_at.desc())
        .limit(1)
    )
    mentioned = {match.upper() for row in rows for match in ORDER_PATTERN.findall(row.content)}
    orders = sorted(mentioned | ({task.order_id} if task else set()))
    context: dict[str, Any] = {
        "message_count": len(rows),
        "orders": orders,
        "workflow_state": task.state if task else None,
        "pending_step": PENDING_STEP.get(task.state, "无") if task else "无",
        "recent_messages": [{"role": row.role, "content": row.content} for row in rows[-10:]],
    }
    existing = await session.scalar(
        select(Handoff).where(
            Handoff.tenant_id == identity.tenant_id,
            Handoff.user_id == identity.user_id,
            Handoff.conversation_id == conversation_id,
        )
    )
    if existing is not None:
        return existing

    handoff = Handoff(
        id=str(uuid4()),
        conversation_id=conversation_id,
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        summary=summary,
        context=context,
        trace_id=trace_id,
    )
    session.add(handoff)
    await session.commit()
    return handoff
