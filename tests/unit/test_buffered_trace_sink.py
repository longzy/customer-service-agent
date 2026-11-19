"""有界缓冲 trace sink：批量 flush、队列满丢弃与关闭 flush。"""

from typing import Any

import pytest

from backend.platform import metrics
from backend.platform.observability import BufferedTraceSink


@pytest.fixture(autouse=True)
def reset_metrics() -> Any:
    metrics.reset()
    yield
    metrics.reset()


async def test_关闭时批量flush开始与完成事件(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = BufferedTraceSink(None, buffer_size=10, flush_interval_ms=1000, batch_size=10)
    batches: list[list[Any]] = []

    async def fake_flush(batch: list[Any]) -> None:
        batches.append(batch)

    monkeypatch.setattr(sink, "_flush", fake_flush)
    token = sink.start(
        tool="get_order",
        identity=object(),
        order_id="ORD-10001",
        idempotency_key=None,
        trace_id="t-1",
        payload={"order_id": "ORD-10001"},
    )
    sink.finish(token, result_status="ok")

    await sink.aclose()

    assert [event.kind for event in batches[0]] == ["start", "finish"]


async def test_队列满丢最旧并计数() -> None:
    sink = BufferedTraceSink(None, buffer_size=1, start_worker=False)

    sink.start(
        tool="get_order",
        identity=object(),
        order_id="ORD-10001",
        idempotency_key=None,
        trace_id="t-1",
        payload={},
    )
    sink.start(
        tool="get_order",
        identity=object(),
        order_id="ORD-10002",
        idempotency_key=None,
        trace_id="t-2",
        payload={},
    )

    assert metrics.snapshot()["trace_dropped_total"] == 1
