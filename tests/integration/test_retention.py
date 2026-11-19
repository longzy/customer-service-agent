"""保留清理：L3/L3.5 可删，L2 审计只报告不删除。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select, text

from backend.platform import metrics
from backend.platform.db import session_factory
from backend.platform.models import (
    ServiceAiEvent,
    ServiceAuditEvent,
    ServiceConversation,
    ServiceCustomer,
    ToolExecution,
)
from backend.platform.retention import cleanup
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)


async def _reset() -> None:
    async with session_factory() as db:
        await db.execute(delete(ToolExecution))
        await db.execute(delete(ServiceAiEvent))
        await db.execute(delete(ServiceConversation))
        await db.execute(delete(ServiceCustomer))
        await db.execute(text("TRUNCATE service_audit_events"))
        await db.commit()


async def _seed() -> None:
    async with session_factory() as db:
        db.add(
            ServiceCustomer(
                id="cust-ret",
                tenant_id="tenant-a",
                username="ret",
                password_hash="x",  # noqa: S106 - 测试种子，不用于登录
                display_name="ret",
                active=True,
            )
        )
        await db.flush()
        db.add(
            ServiceConversation(
                id="conv-ret",
                tenant_id="tenant-a",
                customer_id="cust-ret",
                status="AI_ACTIVE",
                journey_id="journey-ret",
                created_at=NOW,
                updated_at=NOW,
                last_activity_at=NOW,
            )
        )
        await db.flush()
        db.add_all(
            [
                ToolExecution(
                    id="trace-normal",
                    trace_id="trace-normal",
                    tool_name="get_order",
                    tenant_id="tenant-a",
                    user_id="user-a1",
                    input_digest="x",
                    result_status="ok",
                    created_at=NOW - timedelta(days=31),
                ),
                ToolExecution(
                    id="trace-critical",
                    trace_id="trace-critical",
                    tool_name="submit_cancel",
                    tenant_id="tenant-a",
                    user_id="user-a1",
                    input_digest="x",
                    result_status="ok",
                    created_at=NOW - timedelta(days=31),
                ),
                ToolExecution(
                    id="trace-very-old",
                    trace_id="trace-very-old",
                    tool_name="get_order",
                    tenant_id="tenant-a",
                    user_id="user-a1",
                    input_digest="x",
                    result_status="ok",
                    created_at=NOW - timedelta(days=400),
                ),
                ServiceAiEvent(
                    id="ai-normal",
                    conversation_id="conv-ret",
                    journey_id="journey-ret",
                    event_type="model",
                    name="customer_chat",
                    status="ok",
                    trace_id="trace-ai-normal",
                    created_at=NOW - timedelta(days=91),
                ),
                ServiceAiEvent(
                    id="ai-critical",
                    conversation_id="conv-ret",
                    journey_id="journey-ret",
                    event_type="model",
                    name="customer_chat",
                    status="timeout",
                    trace_id="trace-ai-critical",
                    created_at=NOW - timedelta(days=91),
                ),
                ServiceAuditEvent(
                    id="audit-old",
                    tenant_id="tenant-a",
                    actor_type="employee",
                    actor_id="emp-agent_1",
                    event_type="conversation.viewed",
                    entity_type="conversation",
                    entity_id="conv-ret",
                    result_status="viewed",
                    journey_id="journey-ret",
                    trace_id="trace-audit-old",
                    metadata_redacted={},
                    created_at=NOW - timedelta(days=181),
                ),
            ]
        )
        await db.commit()


async def _ids(model: Any) -> set[str]:
    async with session_factory() as db:
        return {str(row) for row in (await db.execute(select(model.id))).scalars()}


async def test_dry_run只统计不删除且审计保留() -> None:
    metrics.reset()
    await _reset()
    await _seed()
    try:
        report = await cleanup(session_factory, now=NOW, apply=False)

        assert report.trace_deleted == 2
        assert report.ai_deleted == 1
        assert report.audit_expired == 1
        assert report.dry_run is True
        assert await _ids(ToolExecution) == {"trace-normal", "trace-critical", "trace-very-old"}
        assert await _ids(ServiceAiEvent) == {"ai-normal", "ai-critical"}
        assert await _ids(ServiceAuditEvent) == {"audit-old"}
    finally:
        await _reset()


async def test_apply删除过期trace与ai但审计只报告() -> None:
    metrics.reset()
    await _reset()
    await _seed()
    try:
        report = await cleanup(session_factory, now=NOW, apply=True)

        assert report.trace_deleted == 2
        assert report.ai_deleted == 1
        assert report.audit_expired == 1
        assert await _ids(ToolExecution) == {"trace-critical"}
        assert await _ids(ServiceAiEvent) == {"ai-critical"}
        assert await _ids(ServiceAuditEvent) == {"audit-old"}
        assert metrics.snapshot()["retention_trace_deleted_total"] == 2
        assert metrics.snapshot()["retention_ai_deleted_total"] == 1
        assert metrics.snapshot()["retention_audit_expired_total"] == 1
    finally:
        await _reset()
