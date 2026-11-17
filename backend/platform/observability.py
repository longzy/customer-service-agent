"""Trace、审计与脱敏：trace 生成、工具写前记录、链路查询与允许清单。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


class TraceSinkError(Exception):
    """审计写入失败；不是 GatewayError，业务错误处理不得吞掉。"""


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


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """结构化日志：只输出允许清单字段，消息/回复正文不会进入日志。"""
    payload = redact_event({"event": event, **fields})
    logger.info(json.dumps(payload, ensure_ascii=False, default=str))


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


class AsyncTraceSink:
    """在 worker 线程通过请求事件循环写 tool_executions。"""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory
        self._loop = asyncio.get_running_loop()

    def _run(self, coro: Any) -> Any:
        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=5)
        except Exception as error:  # noqa: BLE001 - 统一转审计失败
            raise TraceSinkError("审计写入失败") from error

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
        self._run(
            self._write_start(
                execution_id,
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
        self._run(
            self._write_finish(
                execution_id,
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
        self._run(
            self._write_reject(
                tool=tool,
                identity=identity,
                order_id=order_id,
                trace_id=trace_id,
                error_code=error_code,
                payload=payload,
            )
        )

    async def _write_start(
        self,
        execution_id: str,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        idempotency_key: str | None,
        trace_id: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._factory() as session:
            session.add(
                ToolExecution(
                    id=execution_id,
                    trace_id=trace_id,
                    tool_name=tool,
                    tenant_id=identity.tenant_id,
                    user_id=identity.user_id,
                    order_id=order_id,
                    idempotency_key_digest=idempotency_digest(idempotency_key),
                    input_digest=_digest_payload(payload),
                    result_status="started",
                )
            )
            await session.commit()

    async def _write_finish(
        self,
        execution_id: str,
        *,
        result_status: str,
        error_code: str | None,
        response: Any,
        latency_ms: int | None,
    ) -> None:
        async with self._factory() as session:
            row = await session.get(ToolExecution, execution_id)
            if row is None:
                raise TraceSinkError("工具执行记录不存在")
            row.result_status = result_status
            row.error_code = error_code
            row.response_redacted = redact_response(response)
            row.latency_ms = latency_ms
            await session.commit()

    async def _write_reject(
        self,
        *,
        tool: str,
        identity: Any,
        order_id: str | None,
        trace_id: str,
        error_code: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._factory() as session:
            session.add(
                ToolExecution(
                    id=str(uuid4()),
                    trace_id=trace_id,
                    tool_name=tool,
                    tenant_id=identity.tenant_id,
                    user_id=identity.user_id,
                    order_id=order_id,
                    input_digest=_digest_payload(payload),
                    result_status="rejected",
                    error_code=error_code,
                )
            )
            await session.commit()


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
