"""取消五类事件的审计映射（design 5.1 / AC-70）。

- Workflow 只产出领域事件；本模块把事件翻译成 `AuditRecord`，事件字段与
  白名单在 `backend.audit.service` 维护，本模块不另设字段。
- 不含消息正文、支付信息、PII 与原幂等键：metadata 由 `redact_audit_metadata`
  二次过滤，未知字段直接丢弃。
- 写失败语义（503 + 业务回滚）由 HTTP 层用 `audit_or_503` 负责，本模块只做映射，
  避免领域代码依赖 API 错误类型。
"""

from collections.abc import Mapping
from typing import Any

from backend.audit import AuditRecord


def cancellation_record(event: Mapping[str, Any]) -> AuditRecord:
    """把 Workflow 事件转成一条只追加密数据。

    `trace_id` 取任务链路标识，使请求、提交、结果、工具调用可串联；任务缺省的
    conversation_id 等字段为空时不写，避免占位值污染审计。
    """
    metadata = dict(event.get("metadata") or {})
    return AuditRecord(
        tenant_id=str(event["tenant_id"]),
        actor_type=str(event["actor_type"]),
        actor_id=str(event["actor_id"]),
        event_type=str(event["event"]),
        entity_type="cancellation_request",
        entity_id=str(metadata["task_id"]),
        trace_id=str(event["trace_id"]),
        result_status=str(event.get("result_status", "committed")),
        metadata=metadata,
    )
