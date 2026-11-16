"""取消类 Tool：资格判定、幂等提交与结果查询。"""

from collections.abc import Callable
from typing import Any

from services.adapters.oms.port import OmsAccess, OmsPort
from services.domain.orders import OrderDetail
from services.identity import Identity
from services.tools.gateway import ToolGateway, ToolSpec
from services.tools.policy import evaluate_eligibility


def _access(identity: Identity) -> OmsAccess:
    return OmsAccess(tenant_id=identity.tenant_id, user_id=identity.user_id)


def build_cancel_gateway(
    oms: OmsPort,
    audit: Callable[[dict[str, Any]], None] | None = None,
    timeout_seconds: float = 2.0,
) -> ToolGateway:
    def eligibility(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        order = oms.get_order(_access(identity), payload["order_id"])
        return evaluate_eligibility(OrderDetail.model_validate(order)).model_dump()

    def submit(payload: dict[str, Any], identity: Identity, trace_id: str) -> Any:
        state = oms.submit_cancel(
            _access(identity),
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
        oms=oms,
        audit=audit,
        timeout_seconds=timeout_seconds,
    )
