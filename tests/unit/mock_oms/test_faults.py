"""故障规则、注入效果与网关衔接（AC-10、AC-11、AC-12）。"""

from typing import Any

import pytest

from services.domain.errors import ErrorCode
from services.errors import DownstreamInvalidResponse, OrderNotFound
from services.identity import Identity
from services.mock_oms.faults import FaultEngine, FaultRule
from services.mock_oms.service import MockOms
from services.tools.gateway import GatewayError, OwnershipIndex, ToolGateway, ToolSpec

IDENTITY = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")


def test_规则按次数消耗_基座豁免() -> None:
    engine = FaultEngine()
    engine.add(FaultRule(kind="timeout", tool="submit_cancel", times=1))
    assert engine.take("submit_cancel", "ORD-10001") == "timeout"
    assert engine.take("submit_cancel", "ORD-10001") is None


def test_规则按工具与订单匹配_基座豁免() -> None:
    engine = FaultEngine()
    engine.add(FaultRule(kind="timeout", tool="get_order", order_id="ORD-10001"))
    assert engine.take("get_order", "ORD-10002") is None
    assert engine.take("submit_cancel", "ORD-10001") is None
    assert engine.take("get_order", "ORD-10001") == "timeout"


def test_清空规则_基座豁免() -> None:
    engine = FaultEngine()
    engine.add(FaultRule(kind="unavailable"))
    engine.clear()
    assert engine.take("get_order", "ORD-10001") is None


def test_延迟可配置到秒级_基座豁免() -> None:
    engine = FaultEngine()
    engine.add(FaultRule(kind="delay", delay_ms=2500))
    engine.take("submit_cancel")
    assert engine.take_delay_seconds == 2.5


def test_超时故障不写入结果_AC_10() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="timeout", tool="submit_cancel"))
    with pytest.raises(TimeoutError):
        service.submit_cancel("tenant-a", "user-a1", "ORD-10001", "idem-1001-abcdef")
    with pytest.raises(OrderNotFound):
        service.get_cancel_result("tenant-a", "idem-1001-abcdef")


def test_响应丢失时对方已受理_AC_10() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="lost_response", tool="submit_cancel"))
    with pytest.raises(TimeoutError):
        service.submit_cancel("tenant-a", "user-a1", "ORD-10001", "idem-1002-abcdef")
    assert service.get_cancel_result("tenant-a", "idem-1002-abcdef") == "ACCEPTED"


def test_非法响应故障_AC_11() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="invalid_response", tool="get_order"))
    with pytest.raises(DownstreamInvalidResponse):
        service.get_order("tenant-a", "user-a1", "ORD-10001")


def test_连续不可用后恢复_AC_12() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="unavailable", tool="get_order", times=2))
    with pytest.raises(ConnectionError):
        service.get_order("tenant-a", "user-a1", "ORD-10001")
    with pytest.raises(ConnectionError):
        service.get_order("tenant-a", "user-a1", "ORD-10001")
    assert service.get_order("tenant-a", "user-a1", "ORD-10001")["order_id"] == "ORD-10001"


def _gateway(service: MockOms, handler: Any = None) -> ToolGateway:
    index = OwnershipIndex()
    service.build_ownership_index(index)

    def submit(payload: dict[str, Any], identity: Identity, trace_id: str) -> str:
        return service.submit_cancel(
            identity.tenant_id, identity.user_id, payload["order_id"], payload["idempotency_key"]
        )

    return ToolGateway(
        tools=[ToolSpec("submit_cancel", handler or submit)],
        ownership=index,
        audit=lambda event: None,
    )


def test_注入故障后经网关得到依赖超时_AC_12() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="timeout", tool="submit_cancel"))
    with pytest.raises(GatewayError) as exc:
        _gateway(service).invoke(
            "submit_cancel",
            {"order_id": "ORD-10001", "idempotency_key": "idem-2001-abcdef"},
            IDENTITY,
            trace_id="t-1",
        )
    assert exc.value.payload["code"] == ErrorCode.DEPENDENCY_TIMEOUT.value


def test_注入非法响应后经网关归类_AC_11() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="invalid_response", tool="submit_cancel"))
    with pytest.raises(GatewayError) as exc:
        _gateway(service).invoke(
            "submit_cancel",
            {"order_id": "ORD-10001", "idempotency_key": "idem-2002-abcdef"},
            IDENTITY,
            trace_id="t-1",
        )
    assert exc.value.payload["code"] == ErrorCode.INVALID_RESPONSE.value


def test_注入不可用后经网关归类_AC_12() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="unavailable", tool="submit_cancel"))
    with pytest.raises(GatewayError) as exc:
        _gateway(service).invoke(
            "submit_cancel",
            {"order_id": "ORD-10001", "idempotency_key": "idem-2003-abcdef"},
            IDENTITY,
            trace_id="t-1",
        )
    assert exc.value.payload["code"] == ErrorCode.DEPENDENCY_UNAVAILABLE.value


def test_不可取消经网关归类为OMS拒绝_AC_05() -> None:
    service = MockOms()
    with pytest.raises(GatewayError) as exc:
        _gateway(service).invoke(
            "submit_cancel",
            {"order_id": "ORD-10003", "idempotency_key": "idem-2004-abcdef"},
            IDENTITY,
            trace_id="t-1",
        )
    assert exc.value.payload["code"] == ErrorCode.OMS_REJECTED.value


def test_管理接口注入的故障影响应用实例_基座豁免() -> None:
    from fastapi.testclient import TestClient

    from services.api.main import create_app

    with TestClient(create_app()) as api:
        assert (
            api.post(
                "/_admin/faults", json={"kind": "timeout", "tool": "get_order", "times": 1}
            ).status_code
            == 204
        )
        with pytest.raises(TimeoutError):
            api.app.state.oms.get_order("tenant-a", "user-a1", "ORD-10001")


def test_管理接口拒绝非法输入_基座豁免() -> None:
    from fastapi.testclient import TestClient

    from services.api.main import create_app

    with TestClient(create_app()) as api:
        assert api.post("/_admin/faults", json={"kind": "bogus"}).status_code == 422
        assert api.post("/_admin/faults", json={"kind": "timeout", "times": 0}).status_code == 422


def test_生产环境不挂载故障管理接口_基座豁免(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from services.api.main import create_app
    from services.platform.settings import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "model_api_key", "test-key")
    with TestClient(create_app()) as api:
        assert api.post("/_admin/faults", json={"kind": "timeout"}).status_code == 404


def test_幂等回放前先校验归属_AC_09() -> None:
    service = MockOms()
    service.submit_cancel("tenant-a", "user-a1", "ORD-10001", "idem-3001-abcdef")
    with pytest.raises(OrderNotFound):
        service.submit_cancel("tenant-a", "user-a2", "ORD-10001", "idem-3001-abcdef")


def test_取消结果接口对未知键返回404_基座豁免() -> None:
    from fastapi.testclient import TestClient

    from services.api.main import create_app

    with TestClient(create_app()) as api:
        response = api.post(
            "/_admin/cancel-result",
            json={"tenant_id": "tenant-a", "idempotency_key": "nope", "state": "CANCELLED"},
        )
        assert response.status_code == 404
