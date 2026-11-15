"""开发期管理接口：注册与清理 Mock OMS 故障规则。"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from services.mock_oms.faults import FaultRule
from services.mock_oms.service import MockOms

router = APIRouter(prefix="/_admin")
_oms = MockOms()


class FaultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    tool: str | None = None
    order_id: str | None = None
    times: int = 1


@router.post("/faults", status_code=204)
def add_fault(payload: FaultPayload) -> None:
    _oms.faults.add(FaultRule(**payload.model_dump()))


@router.delete("/faults", status_code=204)
def clear_faults() -> None:
    _oms.faults.clear()
