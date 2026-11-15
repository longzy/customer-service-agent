"""故障规则与注入效果（AC-10、AC-11、AC-12）。"""

import pytest

from services.mock_oms.faults import FaultEngine, FaultRule
from services.mock_oms.service import MockOms, MockOmsInvalidResponse, OrderNotFound


def test_规则按次数消耗_AC_10() -> None:
    engine = FaultEngine()
    engine.add(FaultRule(kind="timeout", tool="submit_cancel", times=1))
    assert engine.take("submit_cancel", "ORD-10001") == "timeout"
    assert engine.take("submit_cancel", "ORD-10001") is None


def test_规则按工具与订单匹配_AC_10() -> None:
    engine = FaultEngine()
    engine.add(FaultRule(kind="timeout", tool="get_order", order_id="ORD-10001"))
    assert engine.take("get_order", "ORD-10002") is None
    assert engine.take("submit_cancel", "ORD-10001") is None
    assert engine.take("get_order", "ORD-10001") == "timeout"


def test_清空规则_AC_12() -> None:
    engine = FaultEngine()
    engine.add(FaultRule(kind="unavailable"))
    engine.clear()
    assert engine.take("get_order", "ORD-10001") is None


def test_超时故障不写入结果_AC_10() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="timeout", tool="submit_cancel"))
    with pytest.raises(TimeoutError):
        service.submit_cancel("ORD-10001", "idem-1001-abcdef")
    with pytest.raises(OrderNotFound):
        service.get_cancel_result("idem-1001-abcdef")


def test_响应丢失时对方已受理_AC_10() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="lost_response", tool="submit_cancel"))
    with pytest.raises(TimeoutError):
        service.submit_cancel("ORD-10001", "idem-1002-abcdef")
    assert service.get_cancel_result("idem-1002-abcdef") == "ACCEPTED"


def test_非法响应故障_AC_11() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="invalid_response", tool="get_order"))
    with pytest.raises(MockOmsInvalidResponse):
        service.get_order("tenant-a", "user-a1", "ORD-10001")


def test_连续不可用后恢复_AC_12() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="unavailable", tool="get_order", times=2))
    with pytest.raises(ConnectionError):
        service.get_order("tenant-a", "user-a1", "ORD-10001")
    with pytest.raises(ConnectionError):
        service.get_order("tenant-a", "user-a1", "ORD-10001")
    assert service.get_order("tenant-a", "user-a1", "ORD-10001")["order_id"] == "ORD-10001"


def test_管理接口可注入与清理故障_AC_12() -> None:
    from fastapi.testclient import TestClient

    from services.api.main import create_app

    with TestClient(create_app()) as api:
        assert (
            api.post("/_admin/faults", json={"kind": "timeout", "tool": "get_order"}).status_code
            == 204
        )
        assert api.delete("/_admin/faults").status_code == 204


def test_生产环境不挂载故障管理接口_AC_12(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from services.api.main import create_app
    from services.api.settings import settings

    monkeypatch.setattr(settings, "environment", "production")
    with TestClient(create_app()) as api:
        assert api.post("/_admin/faults", json={"kind": "timeout"}).status_code == 404
