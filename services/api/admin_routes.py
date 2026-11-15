"""开发期管理接口：故障规则与取消结果推进，仅在非生产环境挂载。"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from services.errors import OrderNotFound
from services.mock_oms.faults import FaultKind, FaultRule
from services.mock_oms.service import MockOms

router = APIRouter(prefix="/_admin")

TOOLS = Literal[
    "get_order",
    "list_recent_orders",
    "get_cancel_eligibility",
    "submit_cancel",
    "get_cancel_result",
]
STATES = Literal["ACCEPTED", "CANCELLED", "REJECTED", "UNKNOWN"]


class FaultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FaultKind
    tool: TOOLS | None = None
    order_id: str | None = None
    times: int = Field(default=1, ge=1)
    delay_ms: int = Field(default=0, ge=0, le=10000)


class CancelResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    idempotency_key: str
    state: STATES


def _oms(request: Request) -> MockOms:
    service: MockOms = request.app.state.oms
    return service


@router.post("/faults", status_code=204)
def add_fault(payload: FaultPayload, request: Request) -> None:
    _oms(request).faults.add(FaultRule(**payload.model_dump()))


@router.delete("/faults", status_code=204)
def clear_faults(request: Request) -> None:
    _oms(request).faults.clear()


@router.post("/cancel-result", status_code=204)
def set_cancel_result(payload: CancelResultPayload, request: Request) -> None:
    try:
        _oms(request).set_cancel_result(payload.tenant_id, payload.idempotency_key, payload.state)
    except OrderNotFound as error:
        raise HTTPException(status_code=404, detail="幂等键不存在") from error
