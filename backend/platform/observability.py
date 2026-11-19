"""Trace、审计与脱敏：trace 生成、工具写前记录、链路查询与允许清单。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform import metrics
from backend.platform.models import (
    AuditEvent,
    CancellationRequest,
    Conversation,
    Message,
    ToolExecution,
)

ALLOWED_EVENT_KEYS = frozenset(
    {
        "trace_id",
        "event",
        "tenant_id",
        "user_id",
        "account_id",
        "order_id",
        "task_id",
        "conversation_id",
        "tool",
        "event_type",
        "intent",
        "state",
        "from_state",
        "to_state",
        "action",
        "result_status",
        "error_code",
        "reason_code",
        "latency_ms",
        "idempotency_key_digest",
        "replaced",
        "mismatch",
        "needs_clarification",
        "pending_step",
    }
)
RESPONSE_KEYS = frozenset(
    {"order_id", "order_status", "cancelable", "eligible", "reason_code", "state"}
)


class AuditWriteError(Exception):
    """审计写入失败；不是 GatewayError，业务错误处理不得吞掉。"""


class TraceWriteError(Exception):
    """技术 trace 写入失败；可观测数据，不应阻断业务。"""


def new_trace_id() -> str:
    return str(uuid4())


def idempotency_digest(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _digest_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redact_event(event: dict[str, Any]) -> dict[str, Any]:
    """只保留允许清单中的字段；未知字段直接丢弃，不做模式猜测。"""
    return {
        key: value
        for key, value in event.items()
        if key in ALLOWED_EVENT_KEYS and value is not None
    }


def redact_response(value: Any) -> Any:
    """业务响应只保留状态/资格字段，不保存金额、商品明细或支付信息。"""
    if isinstance(value, dict):
        return {key: item for key, item in value.items() if key in RESPONSE_KEYS}
    if isinstance(value, list):
        return [redact_response(item) for item in value[:20]]
    return None


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any
) -> None:
    """结构化日志：只输出允许清单字段，消息/回复正文不会进入日志。"""
    payload = redact_event({"event": event, **fields})
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))


class TraceSink(Protocol):
    def start(
        self,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        idempotency_key: str | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> str: ...

    def finish(
        self,
        execution_id: str,
        *,
        result_status: str,
        error_code: str | None = None,
        response: Any = None,
        latency_ms: int | None = None,
    ) -> None: ...

    def reject(
        self,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        trace_id: str,
        error_code: str,
        payload: dict[str, Any],
    ) -> None: ...


_current_sink: ContextVar[TraceSink | None] = ContextVar("trace_sink", default=None)


def current_trace_sink() -> TraceSink | None:
    return _current_sink.get()


@contextmanager
def use_trace_sink(sink: TraceSink) -> Iterator[None]:
    token = _current_sink.set(sink)
    try:
        yield
    finally:
        _current_sink.reset(token)


# 有副作用的工具：即使采样率很低也必须留痕。
ALWAYS_SAMPLE_TOOLS = frozenset({"submit_cancel", "get_cancel_result"})
MAX_PENDING_TRACES = 1000


@dataclass(frozen=True)
class _PendingTrace:
    tool: str
    identity: Any
    order_id: str | None
    idempotency_key: str | None
    trace_id: str
    payload: dict[str, Any]


class SampledTraceSink:
    """Tail-based 采样：只在 finish 时决定是否写，错误/关键工具 100%。

    `start` 只把待写信息挂在内存；`finish` 按结果决定调用底层 sink。
    这样正常成功可以按比例丢，异常不会因为 head-based 采样提前丢掉。
    """

    def __init__(self, sink: TraceSink, sample_rate: float = 0.05) -> None:
        self._sink = sink
        self._sample_rate = min(max(sample_rate, 0.0), 1.0)
        self._pending: dict[str, _PendingTrace] = {}
        self._lock = Lock()

    def start(
        self,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        idempotency_key: str | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> str:
        token = str(uuid4())
        with self._lock:
            self._pending[token] = _PendingTrace(
                tool=tool,
                identity=identity,
                order_id=order_id,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                payload=payload,
            )
            if len(self._pending) > MAX_PENDING_TRACES:
                self._pending.pop(next(iter(self._pending)))
                metrics.increment("trace_dropped_total")
        metrics.increment("trace_started_total")
        return token

    def finish(
        self,
        execution_id: str,
        *,
        result_status: str,
        error_code: str | None = None,
        response: Any = None,
        latency_ms: int | None = None,
    ) -> None:
        with self._lock:
            pending = self._pending.pop(execution_id, None)
        if pending is None:
            metrics.increment("trace_dropped_total")
            return
        if not self._should_sample(pending.tool, result_status, error_code):
            metrics.increment("trace_dropped_total")
            return
        metrics.increment("trace_sampled_total")
        inner_id = self._sink.start(
            tool=pending.tool,
            identity=pending.identity,
            order_id=pending.order_id,
            idempotency_key=pending.idempotency_key,
            trace_id=pending.trace_id,
            payload=pending.payload,
        )
        self._sink.finish(
            inner_id,
            result_status=result_status,
            error_code=error_code,
            response=response,
            latency_ms=latency_ms,
        )

    def reject(
        self,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        trace_id: str,
        error_code: str,
        payload: dict[str, Any],
    ) -> None:
        # 拒绝本身就是异常信号，不再采样。
        metrics.increment("trace_sampled_total")
        self._sink.reject(
            tool=tool,
            identity=identity,
            order_id=order_id,
            trace_id=trace_id,
            error_code=error_code,
            payload=payload,
        )

    def _should_sample(self, tool: str, result_status: str, error_code: str | None) -> bool:
        if error_code is not None or result_status != "ok":
            return True
        if tool in ALWAYS_SAMPLE_TOOLS:
            return True
        return random.random() < self._sample_rate  # noqa: S311 - 采样不需要密码学随机


@dataclass(frozen=True)
class _TraceEvent:
    kind: str  # start / finish / reject
    execution_id: str | None
    tool: str
    identity: Any
    order_id: str | None
    idempotency_key: str | None
    trace_id: str
    payload: dict[str, Any]
    result_status: str = ""
    error_code: str | None = None
    response: Any = None
    latency_ms: int | None = None


_TRACE_SENTINEL = object()
logger = logging.getLogger(__name__)


class BufferedTraceSink:
    """有界缓冲 + 批量异步写；trace 是 best-effort，不阻断业务。

    `start/finish/reject` 只入队（线程安全）；后台 writer 在事件循环里按
    `flush_interval_ms` 或积满 `batch_size` 提交一批。队列满时丢最旧并计数；
    应用关闭时 `aclose` 唤醒 writer 并 flush。
    """

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        buffer_size: int = 1000,
        flush_interval_ms: int = 2000,
        batch_size: int = 200,
        start_worker: bool = True,
    ) -> None:
        self._factory = factory
        self._queue: Queue[_TraceEvent | object] = Queue(maxsize=buffer_size)
        self._flush_interval = max(flush_interval_ms, 1) / 1000
        self._batch_size = max(batch_size, 1)
        self._closing = False
        self._wake = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        self._task: asyncio.Task[None] | None = (
            self._loop.create_task(self._writer()) if start_worker else None
        )

    def start(
        self,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        idempotency_key: str | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> str:
        execution_id = str(uuid4())
        self._enqueue(
            _TraceEvent(
                kind="start",
                execution_id=execution_id,
                tool=tool,
                identity=identity,
                order_id=order_id,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                payload=payload,
            )
        )
        return execution_id

    def finish(
        self,
        execution_id: str,
        *,
        result_status: str,
        error_code: str | None = None,
        response: Any = None,
        latency_ms: int | None = None,
    ) -> None:
        self._enqueue(
            _TraceEvent(
                kind="finish",
                execution_id=execution_id,
                tool="",
                identity=None,
                order_id=None,
                idempotency_key=None,
                trace_id="",
                payload={},
                result_status=result_status,
                error_code=error_code,
                response=response,
                latency_ms=latency_ms,
            )
        )

    def reject(
        self,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        trace_id: str,
        error_code: str,
        payload: dict[str, Any],
    ) -> None:
        self._enqueue(
            _TraceEvent(
                kind="reject",
                execution_id=None,
                tool=tool,
                identity=identity,
                order_id=order_id,
                idempotency_key=None,
                trace_id=trace_id,
                payload=payload,
                error_code=error_code,
            )
        )

    async def aclose(self) -> None:
        """停止接收并 flush 队列；由 lifespan 在退出时调用。"""
        self._closing = True
        self._wake.set()
        if self._task is None:
            await self._drain()
            return
        try:
            self._queue.put_nowait(_TRACE_SENTINEL)
        except Full:
            with suppress(Empty):
                self._queue.get_nowait()
            with suppress(Full):
                self._queue.put_nowait(_TRACE_SENTINEL)
        try:
            await self._task
        except Exception:  # noqa: BLE001 - 关闭阶段不再向外抛
            logger.warning("trace.writer_failed", exc_info=True)

    def _enqueue(self, event: _TraceEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except Full:
            with suppress(Empty):
                self._queue.get_nowait()
            with suppress(Full):
                self._queue.put_nowait(event)
            metrics.increment("trace_dropped_total")
        with suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._wake.set)

    async def _writer(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=self._flush_interval)
                self._wake.clear()
                await self._drain()
                if self._closing and self._queue.empty():
                    return
                continue
            if item is _TRACE_SENTINEL:
                await self._drain()
                return
            if not isinstance(item, _TraceEvent):
                continue
            batch: list[_TraceEvent] = [item]
            while len(batch) < self._batch_size:
                try:
                    nxt = self._queue.get_nowait()
                except Empty:
                    break
                if nxt is _TRACE_SENTINEL:
                    await self._flush(batch)
                    await self._drain()
                    return
                if isinstance(nxt, _TraceEvent):
                    batch.append(nxt)
            await self._flush(batch)
            if self._closing and self._queue.empty():
                return

    async def _drain(self) -> None:
        batch: list[_TraceEvent] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            if item is _TRACE_SENTINEL:
                continue
            if isinstance(item, _TraceEvent):
                batch.append(item)
            if len(batch) >= self._batch_size:
                await self._flush(batch)
                batch = []
        if batch:
            await self._flush(batch)

    async def _flush(self, batch: list[_TraceEvent]) -> None:
        if not batch:
            return
        try:
            async with self._factory() as session:
                for event in batch:
                    if event.kind == "start":
                        session.add(self._start_row(event))
                    elif event.kind == "reject":
                        session.add(self._reject_row(event))
                    else:
                        row = await session.get(ToolExecution, event.execution_id)
                        if row is None:
                            metrics.increment("trace_dropped_total")
                            continue
                        row.result_status = event.result_status
                        row.error_code = event.error_code
                        row.response_redacted = redact_response(event.response)
                        row.latency_ms = event.latency_ms
                await session.commit()
            metrics.increment("trace_flush_total")
        except Exception:  # noqa: BLE001 - trace 是可观测数据，失败只记录
            metrics.increment("trace_write_failures_total", len(batch))
            logger.warning("trace.flush_failed", exc_info=True)

    @staticmethod
    def _start_row(event: _TraceEvent) -> ToolExecution:
        identity = event.identity
        return ToolExecution(
            id=event.execution_id or str(uuid4()),
            trace_id=event.trace_id,
            span_id=uuid4().hex[:16],
            parent_span_id=None,
            step="tool",
            sampled=True,
            source="buffered",
            tool_name=event.tool,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            order_id=event.order_id,
            idempotency_key_digest=idempotency_digest(event.idempotency_key),
            input_digest=_digest_payload(event.payload),
            result_status="started",
        )

    @staticmethod
    def _reject_row(event: _TraceEvent) -> ToolExecution:
        identity = event.identity
        return ToolExecution(
            id=str(uuid4()),
            trace_id=event.trace_id,
            span_id=uuid4().hex[:16],
            parent_span_id=None,
            step="tool",
            sampled=True,
            source="buffered",
            tool_name=event.tool,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            order_id=event.order_id,
            input_digest=_digest_payload(event.payload),
            result_status="rejected",
            error_code=event.error_code,
        )


@dataclass(frozen=True)
class TraceView:
    trace_id: str
    tenant_id: str
    messages: list[dict[str, Any]]
    tool_executions: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]
    cancellation: dict[str, Any] | None

    @property
    def events(self) -> list[dict[str, Any]]:
        events = [*self.messages, *self.tool_executions, *self.audit_events]
        return sorted(events, key=lambda event: event["created_at"])

    @property
    def empty(self) -> bool:
        return not self.events and self.cancellation is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "events": self.events,
            "cancellation": self.cancellation,
        }


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def load_trace(session: AsyncSession, trace_id: str, tenant_id: str) -> TraceView:
    """按租户读取一条 trace；未知 trace 返回空视图。"""
    messages = (
        await session.execute(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.trace_id == trace_id,
                Conversation.tenant_id == tenant_id,
            )
            .order_by(Message.created_at)
        )
    ).scalars()
    tools = (
        await session.execute(
            select(ToolExecution)
            .where(ToolExecution.trace_id == trace_id, ToolExecution.tenant_id == tenant_id)
            .order_by(ToolExecution.created_at)
        )
    ).scalars()
    audits = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.trace_id == trace_id, AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.created_at)
        )
    ).scalars()
    task = await session.scalar(
        select(CancellationRequest).where(
            CancellationRequest.trace_id == trace_id,
            CancellationRequest.tenant_id == tenant_id,
        )
    )
    return TraceView(
        trace_id=trace_id,
        tenant_id=tenant_id,
        messages=[
            {
                "kind": "message",
                "role": item.role,
                "content": item.content,
                "conversation_id": item.conversation_id,
                "created_at": _iso(item.created_at),
            }
            for item in messages
        ],
        tool_executions=[
            {
                "kind": "tool",
                "tool": item.tool_name,
                "span_id": item.span_id,
                "parent_span_id": item.parent_span_id,
                "step": item.step,
                "sampled": item.sampled,
                "source": item.source,
                "order_id": item.order_id,
                "result_status": item.result_status,
                "error_code": item.error_code,
                "latency_ms": item.latency_ms,
                "response_redacted": item.response_redacted,
                "created_at": _iso(item.created_at),
            }
            for item in tools
        ],
        audit_events=[
            {
                "kind": "audit",
                "event_type": item.event_type,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "order_id": item.order_id,
                "idempotency_key_digest": item.idempotency_key_digest,
                "result_status": item.result_status,
                "metadata": item.metadata_redacted,
                "created_at": _iso(item.created_at),
            }
            for item in audits
        ],
        cancellation=(
            {
                "task_id": task.id,
                "order_id": task.order_id,
                "state": task.state,
                "trace_id": task.trace_id,
            }
            if task is not None
            else None
        ),
    )
