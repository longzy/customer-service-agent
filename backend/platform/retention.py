"""可观测数据保留与清理：L3 trace / L3.5 AI 事件删除，L2 审计只报告不删除。"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform import metrics
from backend.platform.models import ServiceAiEvent, ServiceAuditEvent, ToolExecution

logger = logging.getLogger(__name__)

# 有副作用的工具即使成功也按“关键 trace”保留更久。
CRITICAL_TOOLS = frozenset({"submit_cancel", "get_cancel_result"})


@dataclass(frozen=True)
class RetentionReport:
    trace_deleted: int
    ai_deleted: int
    audit_expired: int
    dry_run: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def cleanup(
    factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime | None = None,
    apply: bool = False,
    trace_retention_days: int = 30,
    trace_error_retention_days: int = 365,
    ai_retention_days: int = 90,
    ai_critical_retention_days: int = 365,
    audit_retention_days: int = 180,
) -> RetentionReport:
    """统计/删除过期可观测数据；审计永远只统计，不删除。

    L2 审计表有只追加触发器，删除必须走独立归档/DDL 审批；本函数不碰它。
    """
    moment = now or datetime.now(UTC)
    trace_cutoff = moment - timedelta(days=trace_retention_days)
    trace_error_cutoff = moment - timedelta(days=trace_error_retention_days)
    ai_cutoff = moment - timedelta(days=ai_retention_days)
    ai_critical_cutoff = moment - timedelta(days=ai_critical_retention_days)
    audit_cutoff = moment - timedelta(days=audit_retention_days)

    normal_trace = (
        (ToolExecution.result_status == "ok")
        & (~ToolExecution.tool_name.in_(CRITICAL_TOOLS))
        & (ToolExecution.created_at < trace_cutoff)
    )
    old_trace = ToolExecution.created_at < trace_error_cutoff
    normal_ai = (ServiceAiEvent.status == "ok") & (ServiceAiEvent.created_at < ai_cutoff)
    old_ai = (ServiceAiEvent.status != "ok") & (ServiceAiEvent.created_at < ai_critical_cutoff)
    expired_audit = ServiceAuditEvent.created_at < audit_cutoff

    trace_deleted = 0
    ai_deleted = 0
    audit_expired = 0
    async with factory() as db:
        trace_deleted = await _count(db, ToolExecution, normal_trace | old_trace)
        ai_deleted = await _count(db, ServiceAiEvent, normal_ai | old_ai)
        audit_expired = await _count(db, ServiceAuditEvent, expired_audit)
        if apply:
            trace_deleted = await _delete(db, ToolExecution, normal_trace | old_trace)
            ai_deleted = await _delete(db, ServiceAiEvent, normal_ai | old_ai)
            await db.commit()

    metrics.increment("retention_trace_deleted_total", trace_deleted)
    metrics.increment("retention_ai_deleted_total", ai_deleted)
    metrics.increment("retention_audit_expired_total", audit_expired)
    if not apply:
        metrics.increment("retention_dry_run_total")
    logger.info(
        "retention.cleanup trace=%d ai=%d audit_expired=%d dry_run=%s",
        trace_deleted,
        ai_deleted,
        audit_expired,
        not apply,
    )
    return RetentionReport(
        trace_deleted=trace_deleted,
        ai_deleted=ai_deleted,
        audit_expired=audit_expired,
        dry_run=not apply,
    )


async def _count(db: AsyncSession, model: Any, condition: Any) -> int:
    value = await db.scalar(select(func.count()).select_from(model).where(condition))
    return int(value or 0)


async def _delete(db: AsyncSession, model: Any, condition: Any) -> int:
    result = await db.execute(delete(model).where(condition))
    return int(getattr(result, "rowcount", 0) or 0)
