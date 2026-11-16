"""查询类 Tool：把 Mock OMS 接入授权网关。"""

from collections.abc import Callable
from typing import Any

from services.identity import Identity
from services.mock_oms.service import MockOms
from services.tools.gateway import OwnershipIndex, ToolGateway, ToolSpec

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


def build_query_gateway(
    oms: MockOms,
    audit: Callable[[dict[str, Any]], None] | None = None,
) -> ToolGateway:
    """构造查询网关；归属索引由夹具生成，身份来自会话。"""
    index = OwnershipIndex()
    oms.build_ownership_index(index)

    def get_order(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        return oms.get_order(identity.tenant_id, identity.user_id, payload["order_id"])

    def list_recent_orders(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        orders = oms.list_recent_orders(identity.tenant_id, identity.user_id, payload["limit"])
        return [_to_summary(order) for order in orders]

    return ToolGateway(
        tools=[
            ToolSpec("get_order", get_order),
            ToolSpec("list_recent_orders", list_recent_orders, requires_order=False),
        ],
        ownership=index,
        audit=audit,
    )
