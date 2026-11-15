"""取消类 Tool：资格判定、幂等提交与结果查询。"""

from collections.abc import Callable
from typing import Any

from services.api.auth import Identity
from services.api.domain.orders import OrderDetail
from services.mock_oms.service import MockOms
from services.tools.gateway import OwnershipIndex, ToolGateway, ToolSpec
from services.tools.policy import evaluate_eligibility


def build_cancel_gateway(
    oms: MockOms,
    audit: Callable[[dict[str, Any]], None] | None = None,
    timeout_seconds: float = 2.0,
) -> ToolGateway:
    index = OwnershipIndex()
    oms.build_ownership_index(index)

    def eligibility(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        order = oms.get_order(identity.tenant_id, identity.user_id, payload["order_id"])
        return evaluate_eligibility(OrderDetail.model_validate(order)).model_dump()

    def submit(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        state = oms.submit_cancel(
            identity.tenant_id,
            identity.user_id,
            payload["order_id"],
            payload["idempotency_key"],
        )
        return {"state": state}

    def result(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        return {"state": oms.get_cancel_result(identity.tenant_id, payload["idempotency_key"])}

    return ToolGateway(
        tools=[
            ToolSpec("get_cancel_eligibility", eligibility),
            ToolSpec("submit_cancel", submit),
            ToolSpec("get_cancel_result", result, requires_order=False),
        ],
        ownership=index,
        audit=audit,
        timeout_seconds=timeout_seconds,
    )
