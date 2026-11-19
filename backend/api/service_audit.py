"""API 层审计编排：业务事务内写审计，失败回滚并 503；安全事件独立提交。"""

import logging
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.audit import (
    AUTH_FAILED,
    FORBIDDEN,
    RATE_LIMITED,
    AuditRecord,
    AuditUnavailableError,
)
from backend.domain.errors import ErrorCode
from backend.platform.http import client_ip, settings_of

# 401/403/429 的安全事件：状态码 → 事件名与结果状态
SECURITY_EVENTS = {
    401: (AUTH_FAILED, "denied"),
    403: (FORBIDDEN, "denied"),
    429: (RATE_LIMITED, "rate_limited"),
}
# 安全事件实体用请求路径；路径可能超过审计列的 64 字符，截断后由 metadata 保留全量。
ENTITY_ID_LIMIT = 64

logger = logging.getLogger(__name__)


def trace_of(request: Request) -> str:
    """请求关联标识；中间件缺省时生成一次性标识，避免审计写入失败。"""
    return getattr(request.state, "trace_id", None) or str(uuid4())


async def audit_or_503(request: Request, db: AsyncSession, record: AuditRecord) -> None:
    """与业务写同事务追加审计；失败回滚业务并返回 503 `AUDIT_UNAVAILABLE`。"""
    try:
        await request.app.state.audit_writer.record(db, record)
    except AuditUnavailableError:
        await db.rollback()
        raise ApiError(503, ErrorCode.AUDIT_UNAVAILABLE) from None


def security_record(
    request: Request,
    status_code: int,
    code: ErrorCode,
    *,
    actor_type: str = "anonymous",
    actor_id: str = "anonymous",
    metadata: Mapping[str, Any] | None = None,
) -> AuditRecord:
    """构造 401/403/429 安全事件；路径与判定字段进 metadata，实体 id 截断。"""
    event_type, result_status = SECURITY_EVENTS[status_code]
    path = request.url.path
    fields: dict[str, Any] = {
        "path": path,
        "method": request.method,
        "status_code": status_code,
        "error_code": code.value,
        "client_ip": client_ip(request),
    }
    fields.update(metadata or {})
    return AuditRecord(
        tenant_id=settings_of(request).m1_tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        entity_type="http_request",
        entity_id=path[:ENTITY_ID_LIMIT],
        trace_id=trace_of(request),
        result_status=result_status,
        metadata=fields,
    )


async def audit_security_event(
    request: Request,
    status_code: int,
    code: ErrorCode,
    *,
    actor_type: str = "anonymous",
    actor_id: str = "anonymous",
    metadata: Mapping[str, Any] | None = None,
) -> None:
    """best-effort 写安全事件并标记已审计；写失败只记日志，不改写原始响应。

    路由在处理异常时先调用本函数（可带上已知身份），`ApiError` handler 随后跳过
    同一请求，避免 401/403/429 重复审计。
    """
    request.state.security_event_audited = True
    record = security_record(
        request,
        status_code,
        code,
        actor_type=actor_type,
        actor_id=actor_id,
        metadata=metadata,
    )
    try:
        await request.app.state.audit_writer.record_security(record)
    except Exception:  # noqa: BLE001 - 安全事件审计不能改写 401/403/429 响应
        logger.exception("安全事件审计失败 event_type=%s", record.event_type)


async def audit_api_error(request: Request, error: ApiError) -> None:
    """401/403/429 安全事件：路由未记时补记，独立提交，不影响原始响应。"""
    if error.status_code not in SECURITY_EVENTS:
        return
    if getattr(request.state, "security_event_audited", False):
        return
    await audit_security_event(request, error.status_code, error.code)
