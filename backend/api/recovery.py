"""启动恢复：悬挂的取消任务按幂等键收敛，并写取消五类事件（AC-67 / AC-70）。

- 恢复与审计同一次事务：仓储只 flush，整批收敛在末尾一次提交；任一条审计写失败
  则整批回滚，下次启动重试——幂等键查询不会重复提交，因此重试安全。
- 旧 `audit_events` 的状态转换仍由 `audit_transition` 写，保持既有追溯口径；
  `service_audit_events` 由 `on_event` 出口写 `cancellation.*`，避免重启收敛的
  终态没有结果事件。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.audit import audit_transition
from backend.audit import AuditWriter
from backend.conversations.cancellation_audit import cancellation_record
from backend.platform.settings import Settings
from backend.tools.gateway import ToolGateway
from backend.workflows.cancel import CancellationWorkflow, SqlCancellationRepository


async def recover_cancellations(
    session: AsyncSession,
    *,
    gateway: ToolGateway,
    audit_writer: AuditWriter,
    active: Settings,
) -> int:
    """收敛悬挂任务并写事件；返回本轮处理的条数。"""

    async def transition(event: dict[str, Any]) -> None:
        await audit_transition(
            session,
            trace_id=str(event["trace_id"]),
            identity=event["identity"],
            task_id=str(event["task_id"]),
            order_id=str(event["order_id"]),
            from_state=str(event["from_state"]),
            to_state=str(event["to_state"]),
            reason_code=event["reason_code"],
            result_status=str(event["result_status"]),
            idempotency_key=event.get("idempotency_key"),
        )

    async def emit(event: dict[str, Any]) -> None:
        await audit_writer.record(session, cancellation_record(event))

    workflow = CancellationWorkflow(
        SqlCancellationRepository(session, commit_on_save=False),
        gateway,
        confirm_timeout_minutes=active.confirm_timeout_minutes,
        max_retries=active.max_retries,
        retry_backoff_seconds=active.retry_backoff_seconds,
        audit=transition,
        on_event=emit,
    )
    recovered = await workflow.recover_pending()
    await session.commit()
    return recovered
