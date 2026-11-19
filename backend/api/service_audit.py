"""API 层审计编排：业务事务内写审计，失败回滚并 503；安全事件独立提交。"""

import logging
from uuid import uuid4

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.errors import ApiError
from backend.api.session_http import client_ip, settings_of
from backend.audit import AUTH_FAILED, FORBIDDEN, RATE_LIMITED, AuditRecord, AuditUnavailableError
from backend.domain.errors import ErrorCode

SECURITY_EVENTS = {401: AUTH_FAILED, 403: FORBIDDEN, 429: RATE_LIMITED}
SECURITY_RESULT_STATUS = {401: "denied", 403: "denied", 429: "rate_limited"}

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


async def audit_api_error(request: Request, error: ApiError) -> None:
    """401/403/429 安全事件：best-effort，独立提交，不影响原始响应。"""
    event_type = SECURITY_EVENTS.get(error.status_code)
    if event_type is None:
        return
    record = AuditRecord(
        tenant_id=settings_of(request).m1_tenant_id,
        actor_type="anonymous",
        actor_id="anonymous",
        event_type=event_type,
        entity_type="http_request",
        entity_id=request.url.path,
        trace_id=trace_of(request),
        result_status=SECURITY_RESULT_STATUS[error.status_code],
        metadata={
            "path": request.url.path,
            "method": request.method,
            "status_code": error.status_code,
            "error_code": error.code.value,
            "client_ip": client_ip(request),
        },
    )
    try:
        await request.app.state.audit_writer.record_security(record)
    except Exception:  # noqa: BLE001 - 安全事件审计不能改写 401/403/429 响应
        logger.exception("安全事件审计失败 event_type=%s", event_type)
