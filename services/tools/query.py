"""查询类 Tool：把 OMS 端口接入授权网关。"""

from collections.abc import Callable
from typing import Any

from services.adapters.oms.port import OmsAccess, OmsPort
from services.identity import Identity
from services.tools.gateway import ToolGateway, ToolSpec

SUMMARY_FIELDS = (
    "order_id",
    "item_summary",
    "order_status",
    "cancelable",
    "amount_cents",
    "currency",
    "created_at",
)


def _to_summary(order: dict[str, Any]) -> dict[str, Any]:
    """按契约把订单详情投影为摘要，避免把 items 等字段透出。"""
    return {field: order[field] for field in SUMMARY_FIELDS}


def _access(identity: Identity) -> OmsAccess:
    return OmsAccess(tenant_id=identity.tenant_id, user_id=identity.user_id)


def build_query_gateway(
    oms: OmsPort,
    audit: Callable[[dict[str, Any]], None] | None = None,
) -> ToolGateway:
    """构造查询网关；访问上下文由会话身份构造。"""

    def get_order(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        return oms.get_order(_access(identity), payload["order_id"])

    def list_recent_orders(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        orders = oms.list_recent_orders(_access(identity), payload["limit"])
        return [_to_summary(order) for order in orders]

    return ToolGateway(
        tools=[
            ToolSpec("get_order", get_order),
            ToolSpec("list_recent_orders", list_recent_orders, requires_order=False),
        ],
        oms=oms,
        audit=audit,
    )
