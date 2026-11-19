"""有界缓冲 trace 的真实批量写：start + finish 一次提交。"""

from typing import Any

import pytest
from sqlalchemy import delete, select

from backend.adapters.oms.mock import MockOmsAdapter
from backend.identity import Identity
from backend.platform import metrics
from backend.platform.db import trace_session_factory
from backend.platform.models import ToolExecution
from backend.platform.observability import BufferedTraceSink, use_trace_sink
from backend.tools.query import build_query_gateway
from tests.integration.db_support import with_db
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

IDENTITY = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
TRACE_ID = "trace-buffer"


async def _clear() -> None:
    async def action(db: Any) -> None:
        await db.execute(delete(ToolExecution).where(ToolExecution.trace_id == TRACE_ID))
        await db.commit()

    await with_db(action)


async def _rows() -> list[ToolExecution]:
    async def action(db: Any) -> list[ToolExecution]:
        return list(
            (
                await db.execute(select(ToolExecution).where(ToolExecution.trace_id == TRACE_ID))
            ).scalars()
        )

    return await with_db(action)


async def test_缓冲sink批量写工具执行记录_AC_17() -> None:
    metrics.reset()
    await _clear()
    sink = BufferedTraceSink(trace_session_factory, buffer_size=10, flush_interval_ms=1000)
    try:
        with use_trace_sink(sink):
            result = build_query_gateway(MockOmsAdapter()).invoke(
                "get_order", {"order_id": "ORD-10001"}, IDENTITY, TRACE_ID
            )
        assert result["order_id"] == "ORD-10001"

        await sink.aclose()
        rows = await _rows()
        assert len(rows) == 1
        assert rows[0].result_status == "ok"
        assert rows[0].tool_name == "get_order"
        assert metrics.snapshot()["trace_flush_total"] == 1
    finally:
        await _clear()
