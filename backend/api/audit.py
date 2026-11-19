"""旧取消工作流的审计事件写入：与业务写入共用 session，由调用方提交。

只保留 `CancellationWorkflow` 启动恢复仍在使用的 `audit_transition`；
新 M1 的客户/坐席审计走 `backend/audit/service.py`。
"""

from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.identity import Identity
from backend.platform.models import AuditEvent
from backend.platform.observability import idempotency_digest, redact_event


async def record_audit(
    session: AsyncSession,
    *,
    trace_id: str,
    identity: Identity,
    event_type: str,
    entity_type: str,
    entity_id: str,
    result_status: str = "committed",
    order_id: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=str(uuid4()),
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_type="user",
        actor_id=identity.user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        order_id=order_id,
        idempotency_key_digest=idempotency_digest(idempotency_key),
        result_status=result_status,
        metadata_redacted=redact_event(metadata or {}),
    )
    session.add(event)
    return event


async def audit_transition(
    session: AsyncSession,
    *,
    trace_id: str,
    identity: Identity,
    task_id: str,
    order_id: str,
    from_state: str,
    to_state: str,
    reason_code: str | None = None,
    result_status: str = "committed",
    idempotency_key: str | None = None,
) -> None:
    await record_audit(
        session,
        trace_id=trace_id,
        identity=identity,
        event_type="WORKFLOW_TRANSITION",
        entity_type="cancellation_request",
        entity_id=task_id,
        order_id=order_id,
        idempotency_key=idempotency_key,
        result_status=result_status,
        metadata={
            "task_id": task_id,
            "from_state": from_state,
            "to_state": to_state,
            "reason_code": reason_code,
        },
    )
