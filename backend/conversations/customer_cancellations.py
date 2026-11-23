"""客户取消任务：发起、确认、拒绝、结果读取与列表回显。

- 任务状态机、幂等提交与恢复复用 `CancellationWorkflow`，本模块只做客户侧编排：
  归属/资格仍由 Tool Gateway 与 Policy Engine 判定，模型不参与。
- 请求级 UoW：仓储以 `commit_on_save=False` 运行，路由与业务模块只 flush，
  由 `get_session` 统一提交（design 3.2 / ADR-0009）。
- 同一订单只允许一个进行中任务；过期任务在读取/重新发起时惰性收尾，不写 OMS。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.cancellation_access import (
    customer_cancellation_scope,
    ensure_confirmation_allowed,
)
from backend.conversations.order_queries import customer_identity
from backend.domain.cancellation import (
    IN_PROGRESS_STATES,
    CancellationState,
)
from backend.identity.customer_sessions import Customer
from backend.platform.models import CancellationRequest as CancellationRow
from backend.tools.gateway import ToolGateway
from backend.workflows.cancel import (
    CancellationTask,
    CancellationWorkflow,
    InvalidTransition,
    SqlCancellationRepository,
    TaskConflict,
    TaskNotFound,
)

# 列表不展示这些终态：已取消由 OMS 订单状态表达，拒绝/放弃/资格拒绝后按钮恢复可取消。
HIDDEN_FROM_LIST = frozenset(
    {
        CancellationState.ELIGIBILITY_REJECTED,
        CancellationState.CANCELLED,
        CancellationState.REJECTED,
        CancellationState.ABANDONED,
    }
)


class CancellationTaskNotFound(Exception):
    """任务不存在、已跨客户/跨租户；对外统一查无。"""


class CancellationStateConflict(Exception):
    """任务状态不允许本次操作（并发或非法转换）。"""


# 迁移 0014 的部分唯一索引名；并发插入由数据库兜底时据此区分冲突来源。
ACTIVE_ORDER_INDEX = "uq_cancellation_active_order"


def _is_active_order_conflict(error: IntegrityError) -> bool:
    """只把“同订单活跃任务”唯一冲突当并发处理，其他完整性错误照常抛出。"""
    diag = getattr(error.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    if isinstance(name, str):
        return name == ACTIVE_ORDER_INDEX
    return ACTIVE_ORDER_INDEX in str(error.orig)


@dataclass(frozen=True)
class CancellationSnapshot:
    """列表页回显所需的最小任务状态；不携带 OMS 内容。"""

    id: str
    order_id: str
    state: CancellationState
    reason_code: str | None
    expires_at: datetime


def build_workflow(
    db: AsyncSession,
    gateway: ToolGateway | None,
    *,
    confirm_timeout_minutes: int,
    now: datetime,
) -> CancellationWorkflow:
    """请求内工作流：仓储只 flush，提交交给请求级 UoW。"""
    if gateway is None:
        # 应用装配缺失属于部署错误；不给客户猜测结果的机会。
        raise RuntimeError("取消网关不可用")
    return CancellationWorkflow(
        SqlCancellationRepository(db, commit_on_save=False),
        gateway,
        confirm_timeout_minutes=confirm_timeout_minutes,
        now=lambda: now,
    )


def _owned_tasks(customer: Customer) -> Any:
    """客户可见的任务查询：归属过滤只有这一处，列表与复用共用。"""
    return select(CancellationRow).where(
        CancellationRow.tenant_id == customer.tenant_id,
        CancellationRow.user_id == customer.oms_customer_id,
    )


async def _in_progress_task(
    db: AsyncSession, customer: Customer, order_id: str
) -> CancellationSnapshot | None:
    """同一订单进行中的任务；不含已释放的终态。"""
    if not customer.oms_customer_id:
        return None
    row = (
        await db.execute(
            _owned_tasks(customer)
            .where(
                CancellationRow.order_id == order_id,
                CancellationRow.state.in_([state.value for state in IN_PROGRESS_STATES]),
            )
            .order_by(CancellationRow.created_at.desc(), CancellationRow.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return CancellationSnapshot(
        id=row.id,
        order_id=row.order_id,
        state=CancellationState(row.state),
        reason_code=row.reason_code,
        expires_at=row.expires_at,
    )


async def request_cancellation(
    db: AsyncSession,
    gateway: ToolGateway | None,
    customer: Customer,
    order_id: str,
    *,
    trace_id: str,
    now: datetime,
    confirm_timeout_minutes: int,
    conversation_id: str | None = None,
) -> CancellationTask:
    """发起取消；已有进行中任务时复用，过期的等待确认任务先收尾。

    归属/资格由 `get_cancel_eligibility` 网关判定：他人/不存在抛 `GatewayError` 404，
    资格不通过时任务落在 `ELIGIBILITY_REJECTED`，不进入可提交状态。
    """
    workflow = build_workflow(db, gateway, confirm_timeout_minutes=confirm_timeout_minutes, now=now)
    identity = customer_identity(customer)
    existing = await _in_progress_task(db, customer, order_id)
    if existing is not None:
        if existing.state is CancellationState.AWAITING_CONFIRMATION and existing.expires_at <= now:
            # 先 flush 收尾旧任务，再插入新任务，避免部分唯一索引在同一 flush 内冲突。
            await workflow.abandon(identity, existing.id)
            await db.flush()
        else:
            return await workflow.get(identity, existing.id)
    try:
        # 并发插入由数据库唯一索引兜底；savepoint 让冲突只回滚本次插入，
        # 不污染请求级事务（design 3.3 / D-2）。
        async with db.begin_nested():
            return await workflow.request(
                identity,
                order_id,
                trace_id,
                conversation_id,
                requested_by_type="CUSTOMER",
                requested_by_id=customer.id,
            )
    except IntegrityError as error:
        if not _is_active_order_conflict(error):
            raise
        winner = await _in_progress_task(db, customer, order_id)
        if winner is None:
            # 并发方已回滚或任务已离开进行中状态：按冲突返回，不新建。
            raise CancellationStateConflict(order_id) from error
        return await workflow.get(identity, winner.id)


async def latest_awaiting_confirmation(
    db: AsyncSession, customer: Customer
) -> CancellationSnapshot | None:
    """客户最近一个等待确认的任务，按创建时间倒序。

    不过滤过期：过期任务由确认/刷新惰性收尾（design 3.4），聊天短语确认也要
    走同一路径得到“未提交”的确定性结果。
    """
    if not customer.oms_customer_id:
        return None
    row = (
        await db.execute(
            _owned_tasks(customer)
            .where(CancellationRow.state == CancellationState.AWAITING_CONFIRMATION.value)
            .order_by(CancellationRow.created_at.desc(), CancellationRow.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return CancellationSnapshot(
        id=row.id,
        order_id=row.order_id,
        state=CancellationState(row.state),
        reason_code=row.reason_code,
        expires_at=row.expires_at,
    )


async def confirm_cancellation(
    db: AsyncSession,
    gateway: ToolGateway | None,
    customer: Customer,
    task_id: str,
    *,
    now: datetime,
    confirm_timeout_minutes: int,
    confirmation_source: str = "BUTTON",
) -> CancellationTask:
    """客户确认；来源为按钮或固定短语，过期任务结束且不提交。"""
    # 确认只属于客户本人；坐席 actor 在此被拒绝（403），不进入状态机。
    ensure_confirmation_allowed(customer_cancellation_scope(customer))
    workflow = build_workflow(db, gateway, confirm_timeout_minutes=confirm_timeout_minutes, now=now)
    identity = customer_identity(customer)
    try:
        return await workflow.confirm(
            identity,
            task_id,
            confirmation_source=confirmation_source,
            confirmed_by_id=customer.id,
        )
    except TaskNotFound as error:
        raise CancellationTaskNotFound(task_id) from error
    except InvalidTransition:
        # 非确认中状态按幂等读取返回，不猜测新状态。
        try:
            return await workflow.get(identity, task_id)
        except TaskNotFound as error:
            raise CancellationTaskNotFound(task_id) from error
    except TaskConflict as error:
        raise CancellationStateConflict(task_id) from error


async def decline_cancellation(
    db: AsyncSession,
    gateway: ToolGateway | None,
    customer: Customer,
    task_id: str,
    *,
    now: datetime,
    confirm_timeout_minutes: int,
) -> CancellationTask:
    """客户拒绝；重复拒绝幂等，不写 OMS。"""
    # 拒绝同样属于客户本人；坐席无确认/拒绝权限。
    ensure_confirmation_allowed(customer_cancellation_scope(customer))
    workflow = build_workflow(db, gateway, confirm_timeout_minutes=confirm_timeout_minutes, now=now)
    identity = customer_identity(customer)
    try:
        return await workflow.abandon(identity, task_id)
    except TaskNotFound as error:
        raise CancellationTaskNotFound(task_id) from error
    except TaskConflict as error:
        raise CancellationStateConflict(task_id) from error


async def refresh_cancellation(
    db: AsyncSession,
    gateway: ToolGateway | None,
    customer: Customer,
    task_id: str,
    *,
    now: datetime,
    confirm_timeout_minutes: int,
) -> CancellationTask:
    """结果刷新（写）：惰性过期，已受理按 OMS 结果继续推进。"""
    workflow = build_workflow(db, gateway, confirm_timeout_minutes=confirm_timeout_minutes, now=now)
    identity = customer_identity(customer)
    try:
        return await workflow.get(identity, task_id)
    except TaskNotFound as error:
        raise CancellationTaskNotFound(task_id) from error
    except TaskConflict as error:
        raise CancellationStateConflict(task_id) from error


async def list_order_cancellations(
    db: AsyncSession, customer: Customer, order_ids: list[str], *, now: datetime
) -> dict[str, CancellationSnapshot]:
    """按订单回显最新取消任务；已释放终态与过期待确认不出现。

    列表读取保持只读（design 3.2）：过期任务只在读取投影里过滤，不写状态；
    下一次确认/刷新/重新发起时才惰性收尾。
    """
    if not order_ids or not customer.oms_customer_id:
        return {}
    rows = (
        (
            await db.execute(
                _owned_tasks(customer)
                .where(CancellationRow.order_id.in_(order_ids))
                .order_by(CancellationRow.created_at.desc(), CancellationRow.id.desc())
            )
        )
        .scalars()
        .all()
    )
    snapshots: dict[str, CancellationSnapshot] = {}
    for row in rows:
        if row.order_id in snapshots:
            continue
        state = CancellationState(row.state)
        if state in HIDDEN_FROM_LIST:
            continue
        if state is CancellationState.AWAITING_CONFIRMATION and row.expires_at <= now:
            continue
        snapshots[row.order_id] = CancellationSnapshot(
            id=row.id,
            order_id=row.order_id,
            state=state,
            reason_code=row.reason_code,
            expires_at=row.expires_at,
        )
    return snapshots


def can_confirm(snapshot: CancellationSnapshot, now: datetime) -> bool:
    return snapshot.state is CancellationState.AWAITING_CONFIRMATION and now < snapshot.expires_at
