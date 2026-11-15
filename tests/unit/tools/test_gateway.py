"""Tool Gateway：白名单、Schema、归属闸门、错误归一与审计（AC-02、AC-03、AC-14、AC-15）。"""

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from services.api.auth import Identity
from services.api.domain.errors import ErrorCode
from services.tools.gateway import (
    DownstreamInvalidResponse,
    GatewayError,
    OwnershipIndex,
    ToolGateway,
    ToolSpec,
)

IDENTITY = Identity("zhang-ming", "user-a1", "tenant-a", "张明")


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[BaseModel, Identity]] = []
        self.audits: list[dict[str, Any]] = []

    def handler(self, request: BaseModel, identity: Identity) -> dict[str, str]:
        self.calls.append((request, identity))
        return {"order_id": request.model_dump()["order_id"]}

    def audit(self, event: dict[str, Any]) -> None:
        self.audits.append(event)


def gateway_with(recorder: Recorder) -> ToolGateway:
    ownership = OwnershipIndex()
    ownership.register("ORD-10001", "tenant-a", "user-a1")
    return ToolGateway(
        tools=[ToolSpec("get_order", OrderRequest, recorder.handler, requires_order=True)],
        ownership=ownership,
        audit=recorder.audit,
    )


def test_白名单外的工具被拒绝_AC_14() -> None:
    recorder = Recorder()
    gateway = gateway_with(recorder)
    with pytest.raises(GatewayError) as exc:
        gateway.invoke("delete_everything", {"order_id": "ORD-10001"}, IDENTITY)
    assert exc.value.status_code == 404
    assert recorder.calls == []


@pytest.mark.parametrize(
    "payload",
    [{"order_id": "ORD-10001", "extra": 1}, {"order_id": 1}, {}],
)
def test_非法输入被拒绝且不执行_AC_14(payload: dict[str, Any]) -> None:
    recorder = Recorder()
    gateway = gateway_with(recorder)
    with pytest.raises(GatewayError) as exc:
        gateway.invoke("get_order", payload, IDENTITY)
    assert exc.value.status_code == 422
    assert recorder.calls == []


def test_越权订单返回统一错误且不执行_AC_02() -> None:
    recorder = Recorder()
    gateway = gateway_with(recorder)
    with pytest.raises(GatewayError) as exc:
        gateway.invoke("get_order", {"order_id": "ORD-99999"}, IDENTITY)
    assert exc.value.status_code == 404
    assert exc.value.payload["code"] == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value
    assert recorder.calls == []


def test_跨租户订单被拒绝_AC_03() -> None:
    recorder = Recorder()
    gateway = gateway_with(recorder)
    other = Identity("wang-qiang", "user-b1", "tenant-b", "王强")
    with pytest.raises(GatewayError):
        gateway.invoke("get_order", {"order_id": "ORD-10001"}, other)
    assert recorder.calls == []


def test_合法调用注入可信身份_AC_15() -> None:
    recorder = Recorder()
    gateway = gateway_with(recorder)
    result = gateway.invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY)
    assert result == {"order_id": "ORD-10001"}
    request, identity = recorder.calls[0]
    assert identity is IDENTITY
    assert request.order_id == "ORD-10001"


def test_请求体不得覆盖租户_AC_15() -> None:
    recorder = Recorder()
    gateway = gateway_with(recorder)
    with pytest.raises(GatewayError) as exc:
        gateway.invoke(
            "get_order",
            {"order_id": "ORD-10001", "tenant_id": "tenant-b"},
            IDENTITY,
        )
    assert exc.value.status_code == 422
    assert recorder.calls == []


def test_下游超时被归一化为依赖超时_AC_14() -> None:
    recorder = Recorder()

    def timeout_handler(request: BaseModel, identity: Identity) -> None:
        raise TimeoutError

    ownership = OwnershipIndex()
    ownership.register("ORD-10001", "tenant-a", "user-a1")
    gateway = ToolGateway(
        tools=[ToolSpec("get_order", OrderRequest, timeout_handler, requires_order=True)],
        ownership=ownership,
        audit=recorder.audit,
    )
    with pytest.raises(GatewayError) as exc:
        gateway.invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY)
    assert exc.value.payload["code"] == ErrorCode.DEPENDENCY_TIMEOUT.value
    assert exc.value.payload["retryable"] is True


def test_下游非法响应被归类为未知_AC_14() -> None:
    recorder = Recorder()

    def bad_handler(request: BaseModel, identity: Identity) -> None:
        raise DownstreamInvalidResponse("bad payload")

    ownership = OwnershipIndex()
    ownership.register("ORD-10001", "tenant-a", "user-a1")
    gateway = ToolGateway(
        tools=[ToolSpec("get_order", OrderRequest, bad_handler, requires_order=True)],
        ownership=ownership,
        audit=recorder.audit,
    )
    with pytest.raises(GatewayError) as exc:
        gateway.invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY)
    assert exc.value.payload["code"] == ErrorCode.INVALID_RESPONSE.value


def test_每次调用产生审计事件_AC_14() -> None:
    recorder = Recorder()
    gateway = gateway_with(recorder)
    gateway.invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY)
    assert recorder.audits, "成功调用必须产生审计事件"
    event = recorder.audits[-1]
    assert event["tool"] == "get_order"
    assert event["tenant_id"] == "tenant-a"
    assert event["result"] == "ok"
    with pytest.raises(GatewayError):
        gateway.invoke("get_order", {"order_id": "ORD-99999"}, IDENTITY)
    assert recorder.audits[-1]["result"] == "rejected"


def test_下游未知异常归一化为内部错误_AC_14() -> None:
    recorder = Recorder()

    def boom(request: BaseModel, identity: Identity) -> None:
        raise RuntimeError("unexpected")

    ownership = OwnershipIndex()
    ownership.register("ORD-10001", "tenant-a", "user-a1")
    gateway = ToolGateway(
        tools=[ToolSpec("get_order", OrderRequest, boom, requires_order=True)],
        ownership=ownership,
        audit=recorder.audit,
    )
    with pytest.raises(GatewayError) as exc:
        gateway.invoke("get_order", {"order_id": "ORD-10001"}, IDENTITY)
    assert exc.value.payload["code"] == ErrorCode.INTERNAL_ERROR.value
    assert exc.value.payload["visible"] is False
