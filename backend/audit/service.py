"""M1 审计写入：只追加、与业务写同事务、失败可判定。

- 事件清单与字段来自 plan 5.1/3.2；本模块不记录消息正文、密码或 token。
- `record()` 与业务写共用调用方的 session，只 flush，由 API 层统一 commit；
  写失败统一转 `AuditUnavailableError`，由 API 层回滚业务并返回 503。
- `record_security()` 用于 401/403/429 这类发生在认证之前、没有业务事务的事件：
  独立 session 提交，best-effort，写失败只记日志，不改写原始响应。
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform.models import ServiceAuditEvent

logger = logging.getLogger(__name__)

# plan 5.1 的事件清单；客户普通消息补 `message.sent`（plan 3.4 要求 message + audit）
CUSTOMER_LOGIN = "customer.login"
CUSTOMER_LOGOUT = "customer.logout"
EMPLOYEE_LOGIN = "employee.login"
EMPLOYEE_LOGOUT = "employee.logout"
HANDOFF_CREATED = "handoff.created"
HANDOFF_CLAIMED = "handoff.claimed"
CONVERSATION_TAKEN_OVER = "conversation.taken_over"
MESSAGE_SENT = "message.sent"
MESSAGE_REPLIED = "message.replied"
AI_REPLIED = "ai.replied"
CONVERSATION_CLOSED = "conversation.closed"
CONVERSATION_RETURNED_TO_AI = "conversation.returned_to_ai"
AUTH_FAILED = "auth.failed"
RATE_LIMITED = "rate_limited"
FORBIDDEN = "forbidden"

# 审计 metadata 允许清单：只放标识与判定结果，不放正文/凭据。
AUDIT_METADATA_KEYS = frozenset(
    {
        "conversation_id",
        "handoff_id",
        "message_id",
        "from_status",
        "to_status",
        "path",
        "method",
        "status_code",
        "error_code",
        "username",
        "client_ip",
        "reason",
        "trigger",
    }
)
AUDIT_METADATA_STRING_LIMIT = 200


class AuditUnavailableError(Exception):
    """审计写入失败；调用方必须回滚业务并返回 503 `AUDIT_UNAVAILABLE`。"""


@dataclass(frozen=True)
class AuditRecord:
    """一条审计事件；`journey_id` 为空表示与某次客户旅程无关（如登录前失败）。"""

    tenant_id: str
    actor_type: str
    actor_id: str
    event_type: str
    entity_type: str
    entity_id: str
    trace_id: str
    result_status: str = "committed"
    journey_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def redact_audit_metadata(metadata: Mapping[str, Any]) -> dict[str, object]:
    """只保留允许清单内的字段；长字符串截断，未知字段直接丢弃。"""
    redacted: dict[str, object] = {}
    for key, value in metadata.items():
        if key not in AUDIT_METADATA_KEYS or value is None:
            continue
        if isinstance(value, str):
            redacted[key] = value[:AUDIT_METADATA_STRING_LIMIT]
        else:
            redacted[key] = value
    return redacted


def _row(record: AuditRecord, now: datetime) -> ServiceAuditEvent:
    return ServiceAuditEvent(
        id=str(uuid4()),
        tenant_id=record.tenant_id,
        actor_type=record.actor_type,
        actor_id=record.actor_id,
        event_type=record.event_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        result_status=record.result_status,
        journey_id=record.journey_id,
        trace_id=record.trace_id,
        metadata_redacted=redact_audit_metadata(record.metadata),
        created_at=now,
    )


class AuditWriter(Protocol):
    async def record(self, db: AsyncSession, record: AuditRecord) -> None: ...

    async def record_security(self, record: AuditRecord) -> None: ...


class SqlAuditWriter:
    """默认实现：业务事务内追加事件；安全事件用独立 session 提交。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, db: AsyncSession, record: AuditRecord) -> None:
        db.add(_row(record, datetime.now(UTC)))
        try:
            await db.flush()
        except SQLAlchemyError as error:
            raise AuditUnavailableError from error

    async def record_security(self, record: AuditRecord) -> None:
        try:
            async with self._session_factory() as db:
                db.add(_row(record, datetime.now(UTC)))
                await db.commit()
        except SQLAlchemyError:
            # 安全事件写失败不能把 401/403/429 变成 503：保留原始响应，留下日志。
            logger.exception("安全事件审计写入失败 event_type=%s", record.event_type)
