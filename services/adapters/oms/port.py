"""OMS 端口与访问上下文。

业务模块只依赖本文件；具体 Adapter 由 factory 选择（T-25）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

CANCEL_RESULT_STATES = frozenset({"ACCEPTED", "CANCELLED", "REJECTED", "UNKNOWN"})


@dataclass(frozen=True)
class OmsAccess:
    """一次 OMS 调用的访问上下文。

    - 员工：`user_id` 非空，按 `(tenant_id, user_id)` 判归属。
    - 匿名客户（M1）：`user_id=None`，`verified_order_ids` 来自会话内的订单校验。
    """

    tenant_id: str
    user_id: str | None = None
    verified_order_ids: frozenset[str] = frozenset()


class OmsPort(Protocol):
    def is_visible(self, access: OmsAccess, order_id: str) -> bool: ...

    def get_order(self, access: OmsAccess, order_id: str) -> dict[str, Any]: ...

    def list_recent_orders(self, access: OmsAccess, limit: int = 5) -> list[dict[str, Any]]: ...

    def submit_cancel(self, access: OmsAccess, order_id: str, idempotency_key: str) -> str: ...

    def get_cancel_result(self, tenant_id: str, idempotency_key: str) -> str: ...
