"""坐席工作台：会话归属门禁、待接入队列、条件领取、接管、上下文与回复。

- 归属读取只允许同租户且 `assigned_employee_id` 为本人的会话；其余返回 None。
- 队列只返回同租户 `status='QUEUED'` 的交接单，按 `created_at, id` 升序。
- 队列摘要在读取时派生：客户账号/显示名、等待秒数、原因、订单数、脱敏末条；
  不返回完整消息或交接单上下文（plan 3.3.5）。
- 领取是条件写：只有 `QUEUED` 交接单能被领取，同事务把会话归属写给本人并写
  “正在接入人工”系统消息（plan 3.4）。
- 接管是条件写：只允许 `claimed_by=本人` 且 `CLAIMED` 的交接单，同事务把会话
  改为 `HUMAN_ACTIVE`、交接单改为 `ACTIVE`，并写“人工已接入”系统消息。
- 上下文读取只展示交接单里的快照（客户账号、最近 20 条脱敏消息、AI 轨迹、待办），
  不额外暴露未领取时的完整消息。
- 回复只在 `HUMAN_ACTIVE` 会话写入 `agent` 消息；`(conversation_id, idempotency_key)`
  唯一约束保证重放不产生重复；消息读取对归属坐席开放所有状态。
- 本模块只 flush/execute，由 API 层统一 commit，失败由调用方回滚。
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ScalarSelect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.customer_chat import MessageView, list_messages, view_message
from backend.conversations.customer_conversations import latest_message_id
from backend.conversations.handoffs import (
    ORDER_CONTEXT_EMPTY,
    ORDER_CONTEXT_OK,
    redact_text,
)
from backend.conversations.statuses import (
    CLAIMED,
    CLOSED,
    HANDOFF_ACTIVE,
    HUMAN_ACTIVE,
    QUEUED,
)
from backend.platform.models import (
    ServiceConversation,
    ServiceCustomer,
    ServiceHandoff,
    ServiceMessage,
)

QUEUE_LAST_MESSAGE_CHAR_LIMIT = 100
CLAIMING_NOTICE = "正在接入人工"
TAKEOVER_NOTICE = "人工已接入"


class ClaimConflictError(Exception):
    """交接单已不再是 `QUEUED`：被其他坐席领取或状态已变化。"""


class HandoffClosedError(Exception):
    """交接单或会话已关闭，不再接受领取/接管；对应 409 `CONVERSATION_CLOSED`。"""


@dataclass(frozen=True)
class WorkspaceCustomer:
    username: str
    display_name: str


@dataclass(frozen=True)
class HandoffDetail:
    id: str
    status: str
    reason: str
    summary: str
    pending_step: str | None
    order_count: int
    order_context_status: str
    orders: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    ai_trace: list[dict[str, Any]]
    failure_count: int | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class WorkspaceConversationDetail:
    id: str
    status: str
    customer: WorkspaceCustomer
    handoff: HandoffDetail | None


@dataclass(frozen=True)
class ClaimedHandoff:
    handoff_id: str
    conversation_id: str
    status: str
    journey_id: str


@dataclass(frozen=True)
class TakenOverConversation:
    conversation_id: str
    status: str
    journey_id: str


@dataclass(frozen=True)
class ConversationMessages:
    """归属坐席的增量消息页；`after_id` 是下一次轮询游标。"""

    conversation_id: str
    status: str
    messages: list[MessageView]
    after_id: int


@dataclass(frozen=True)
class ReplyResult:
    """坐席回复；重放幂等键时 `message` 为首次落库的那条。"""

    conversation_id: str
    status: str
    message: MessageView
    journey_id: str
    replayed: bool = False


@dataclass(frozen=True)
class QueueItem:
    handoff_id: str
    conversation_id: str
    customer_username: str
    customer_display_name: str
    waiting_seconds: int
    reason: str
    order_count: int
    last_message: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _handoff_detail(handoff: ServiceHandoff) -> HandoffDetail:
    """把交接单里的 JSON 快照投影成读模型；缺字段按空值处理，不猜业务含义。"""
    context = handoff.context or {}
    last_error = context.get("last_error")
    orders = _dict_list(context.get("orders"))
    status = context.get("order_context_status")
    if not isinstance(status, str):
        # 旧交接单没有状态字段：按订单明细是否存在推断，避免把“暂无订单”
        # 误显示为“不可用”。
        status = ORDER_CONTEXT_OK if orders else ORDER_CONTEXT_EMPTY
    return HandoffDetail(
        id=handoff.id,
        status=handoff.status,
        reason=handoff.reason,
        summary=handoff.summary or "",
        pending_step=handoff.pending_step,
        order_count=_int_value(context.get("order_count")),
        order_context_status=status,
        orders=orders,
        messages=_dict_list(context.get("messages")),
        ai_trace=_dict_list(context.get("ai_trace")),
        failure_count=_optional_int(context.get("failure_count")),
        last_error=last_error if isinstance(last_error, str) else None,
    )


async def get_assigned_conversation_detail(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
) -> WorkspaceConversationDetail | None:
    """读取已归属本人的会话；客户与最近一张交接单在同一读模型里。

    未领取、他人领取或跨租户统一返回 None（API 映射 404，不泄露是否存在）。
    交接单按创建时间取最新一张：关闭/转回 AI 后旧单仍在，读模型展示最近一次转人工。
    """
    row = (
        await db.execute(
            select(ServiceConversation, ServiceCustomer)
            .join(ServiceCustomer, ServiceCustomer.id == ServiceConversation.customer_id)
            .where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
                ServiceCustomer.tenant_id == tenant_id,
            )
        )
    ).one_or_none()
    if row is None:
        return None

    conversation, customer = row
    handoff = (
        await db.execute(
            select(ServiceHandoff)
            .where(
                ServiceHandoff.conversation_id == conversation_id,
                ServiceHandoff.tenant_id == tenant_id,
            )
            .order_by(ServiceHandoff.created_at.desc(), ServiceHandoff.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return WorkspaceConversationDetail(
        id=conversation.id,
        status=conversation.status,
        customer=WorkspaceCustomer(
            username=customer.username,
            display_name=customer.display_name,
        ),
        handoff=_handoff_detail(handoff) if handoff is not None else None,
    )


def _waiting_seconds(created_at: datetime, now: datetime) -> int:
    return max(0, int((now - created_at).total_seconds()))


def _last_customer_message() -> ScalarSelect[str]:
    """相关标量子查询：每个会话最后一条客户消息；系统“排队中”提示不占用摘要。"""
    return (
        select(ServiceMessage.content)
        .where(
            ServiceMessage.conversation_id == ServiceHandoff.conversation_id,
            ServiceMessage.author_type == "customer",
        )
        .order_by(ServiceMessage.id.desc())
        .limit(1)
        .correlate(ServiceHandoff)
        .scalar_subquery()
    )


async def list_queued_handoffs(db: AsyncSession, tenant_id: str) -> list[QueueItem]:
    statement = (
        select(ServiceHandoff, ServiceCustomer, _last_customer_message())
        .join(ServiceCustomer, ServiceCustomer.id == ServiceHandoff.customer_id)
        .where(
            ServiceHandoff.tenant_id == tenant_id,
            ServiceHandoff.status == QUEUED,
            ServiceCustomer.tenant_id == tenant_id,
        )
        .order_by(ServiceHandoff.created_at, ServiceHandoff.id)
    )
    rows = (await db.execute(statement)).all()
    now = utc_now()
    return [
        QueueItem(
            handoff_id=handoff.id,
            conversation_id=handoff.conversation_id,
            customer_username=customer.username,
            customer_display_name=customer.display_name,
            waiting_seconds=_waiting_seconds(handoff.created_at, now),
            reason=handoff.reason,
            # F-28：队列订单数取交接单快照的真实值（plan 3.5）。
            order_count=_int_value((handoff.context or {}).get("order_count")),
            last_message=redact_text(last_message or "")[:QUEUE_LAST_MESSAGE_CHAR_LIMIT],
        )
        for handoff, customer, last_message in rows
    ]


async def claim_handoff(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    handoff_id: str,
    *,
    trace_id: str,
) -> ClaimedHandoff | None:
    """条件领取：并发下只有一个事务能把同一交接单从 `QUEUED` 改为 `CLAIMED`。

    - 不存在或跨租户返回 None（API 映射 404，不区分“不存在”与“无权”）。
    - 已关闭抛 `HandoffClosedError`，其余非 `QUEUED` 抛 `ClaimConflictError`。
    - 先读状态是为了给出可区分的错误码；真正防竞态的是带 `status='QUEUED'`
      的 `UPDATE ... RETURNING`。Postgres 在行锁释放后重新评估条件，影响 0 行
      即说明另一个事务已领取。
    - 同事务把会话改为 `CLAIMED`、写 `assigned_employee_id`，并写“正在接入人工”
      系统消息（plan 3.4；不写审计，审计由 F-13 负责）。
    """
    row = (
        await db.execute(
            select(ServiceHandoff.status, ServiceHandoff.conversation_id).where(
                ServiceHandoff.id == handoff_id,
                ServiceHandoff.tenant_id == tenant_id,
            )
        )
    ).one_or_none()
    if row is None:
        return None

    status, conversation_id = row
    if status == CLOSED:
        raise HandoffClosedError
    if status != QUEUED:
        raise ClaimConflictError

    now = utc_now()
    claimed = (
        await db.execute(
            update(ServiceHandoff)
            .where(
                ServiceHandoff.id == handoff_id,
                ServiceHandoff.tenant_id == tenant_id,
                ServiceHandoff.status == QUEUED,
            )
            .values(
                status=CLAIMED,
                claimed_by=employee_id,
                claimed_at=now,
                version=ServiceHandoff.version + 1,
                updated_at=now,
            )
            .returning(ServiceHandoff.id)
        )
    ).scalar_one_or_none()
    if claimed is None:
        raise ClaimConflictError

    conversation = (
        await db.execute(
            update(ServiceConversation)
            .where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.status == QUEUED,
            )
            .values(
                status=CLAIMED,
                assigned_employee_id=employee_id,
                updated_at=now,
            )
            .returning(ServiceConversation.id, ServiceConversation.journey_id)
        )
    ).one_or_none()
    if conversation is None:
        # 交接单与会话状态应由 F-03 同事务维护；出现分歧时整体回滚，不留下半领取。
        raise ClaimConflictError

    db.add(
        ServiceMessage(
            conversation_id=conversation_id,
            author_type="system",
            author_id=None,
            content=CLAIMING_NOTICE,
            idempotency_key=None,
            trace_id=trace_id,
            created_at=now,
        )
    )
    await db.flush()

    return ClaimedHandoff(
        handoff_id=handoff_id,
        conversation_id=conversation_id,
        status=CLAIMED,
        journey_id=conversation.journey_id,
    )


async def take_over_conversation(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
    *,
    trace_id: str,
) -> TakenOverConversation | None:
    """领取者接管：会话 `CLAIMED → HUMAN_ACTIVE`、交接单 `CLAIMED → ACTIVE`。

    - 只处理同租户且 `assigned_employee_id` 为本人的会话；其余返回 None（404）。
    - 已关闭会话抛 `HandoffClosedError`（409 `CONVERSATION_CLOSED`）。
    - 非 `CLAIMED`（未领取或已接管）返回 None，与 plan 3.3.5 的“无行 404”一致。
    - 两个条件更新在同事务内完成；交接单行被并发改走时不再更新会话。
    - 写系统消息“人工已接入”；审计留给 F-13。
    """
    current = (
        await db.execute(
            select(ServiceConversation.status, ServiceConversation.journey_id).where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
            )
        )
    ).one_or_none()
    if current is None:
        return None
    status, journey_id = current
    if status == CLOSED:
        raise HandoffClosedError
    if status != CLAIMED:
        return None

    handoff_id = (
        await db.execute(
            select(ServiceHandoff.id)
            .where(
                ServiceHandoff.conversation_id == conversation_id,
                ServiceHandoff.tenant_id == tenant_id,
                ServiceHandoff.claimed_by == employee_id,
                ServiceHandoff.status == CLAIMED,
            )
            .order_by(ServiceHandoff.created_at.desc(), ServiceHandoff.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if handoff_id is None:
        return None

    now = utc_now()
    updated_handoff = (
        await db.execute(
            update(ServiceHandoff)
            .where(
                ServiceHandoff.id == handoff_id,
                ServiceHandoff.tenant_id == tenant_id,
                ServiceHandoff.claimed_by == employee_id,
                ServiceHandoff.status == CLAIMED,
            )
            .values(
                status=HANDOFF_ACTIVE,
                version=ServiceHandoff.version + 1,
                updated_at=now,
            )
            .returning(ServiceHandoff.id)
        )
    ).scalar_one_or_none()
    if updated_handoff is None:
        return None

    updated_conversation = (
        await db.execute(
            update(ServiceConversation)
            .where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
                ServiceConversation.status == CLAIMED,
            )
            .values(status=HUMAN_ACTIVE, updated_at=now)
            .returning(ServiceConversation.id)
        )
    ).scalar_one_or_none()
    if updated_conversation is None:
        # 会话状态在读取后被并发改走：整体回滚，不留下已 ACTIVE 的交接单。
        raise ClaimConflictError

    db.add(
        ServiceMessage(
            conversation_id=conversation_id,
            author_type="system",
            author_id=None,
            content=TAKEOVER_NOTICE,
            idempotency_key=None,
            trace_id=trace_id,
            created_at=now,
        )
    )
    await db.flush()
    return TakenOverConversation(
        conversation_id=conversation_id,
        status=HUMAN_ACTIVE,
        journey_id=journey_id,
    )


async def read_conversation_messages(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
    after_id: int,
) -> ConversationMessages | None:
    """读取归属坐席会话的增量消息；未领取/他人/跨租户返回 None（404）。

    - 归属校验只认 `assigned_employee_id`，不区分“不存在”与“无权”。
    - 所有会话状态都可读：关闭后坐席仍可回看历史（只读由写接口限制）。
    - 无增量时把游标推进到最后一条消息 id，避免同一批消息被反复返回。
    """
    status = (
        await db.execute(
            select(ServiceConversation.status).where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
            )
        )
    ).scalar_one_or_none()
    if status is None:
        return None
    messages = await list_messages(db, conversation_id, after_id)
    latest = (
        messages[-1].id if messages else max(after_id, await latest_message_id(db, conversation_id))
    )
    return ConversationMessages(
        conversation_id=conversation_id,
        status=status,
        messages=messages,
        after_id=latest,
    )


async def reply_to_conversation(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
    *,
    content: str,
    idempotency_key: str,
    trace_id: str,
    now: datetime,
) -> ReplyResult | None:
    """坐席回复：只在 `HUMAN_ACTIVE` 会话写入 `agent` 消息，不改变会话状态。

    - 未领取/他人/跨租户返回 None（404），与“不存在”不可区分。
    - 已关闭抛 `HandoffClosedError`（409 `CONVERSATION_CLOSED`）。
    - 本人但未接管（`CLAIMED`）返回 None：plan 状态机只定义 `HUMAN_ACTIVE` 可回复。
    - 幂等：同一 `(conversation_id, idempotency_key)` 重放返回首次落库的消息。
    - 先条件更新会话活跃时间再插消息：状态在读取后被并发改走时整体失败，不留下半条回复。
    """
    current = (
        await db.execute(
            select(ServiceConversation.status, ServiceConversation.journey_id).where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
            )
        )
    ).one_or_none()
    if current is None:
        return None
    status, journey_id = current
    if status == CLOSED:
        raise HandoffClosedError
    if status != HUMAN_ACTIVE:
        return None

    replay = (
        await db.execute(
            select(ServiceMessage).where(
                ServiceMessage.conversation_id == conversation_id,
                ServiceMessage.author_type == "agent",
                ServiceMessage.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if replay is not None:
        return ReplyResult(
            conversation_id=conversation_id,
            status=status,
            message=view_message(replay),
            journey_id=journey_id,
            replayed=True,
        )

    updated = (
        await db.execute(
            update(ServiceConversation)
            .where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == tenant_id,
                ServiceConversation.assigned_employee_id == employee_id,
                ServiceConversation.status == HUMAN_ACTIVE,
            )
            .values(updated_at=now, last_activity_at=now)
            .returning(ServiceConversation.id)
        )
    ).scalar_one_or_none()
    if updated is None:
        # 读取后会话被并发关闭/转回；对回复而言已不可写，按 409 处理。
        raise HandoffClosedError

    message = ServiceMessage(
        conversation_id=conversation_id,
        author_type="agent",
        author_id=employee_id,
        content=content,
        idempotency_key=idempotency_key,
        trace_id=trace_id,
        created_at=now,
    )
    db.add(message)
    await db.flush()
    return ReplyResult(
        conversation_id=conversation_id,
        status=HUMAN_ACTIVE,
        message=view_message(message),
        journey_id=journey_id,
    )
