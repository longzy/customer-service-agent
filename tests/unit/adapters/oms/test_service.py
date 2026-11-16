"""Mock OMS：夹具、读写、幂等与归属（AC-01、AC-09、AC-10）。"""

import copy

import pytest

from services.adapters.oms.mock import MockOmsAdapter
from services.adapters.oms.port import OmsAccess
from services.errors import CancelRejected, IdempotencyConflict, OrderNotFound


def access(tenant: str = "tenant-a", user: str = "user-a1") -> OmsAccess:
    return OmsAccess(tenant_id=tenant, user_id=user)


def oms() -> MockOmsAdapter:
    return MockOmsAdapter()


def test_夹具覆盖两租户四种状态与跨用户订单_AC_01() -> None:
    service = oms()
    statuses = {
        service.get_order(access(), oid)["order_status"]
        for oid in ("ORD-10001", "ORD-10002", "ORD-10003", "ORD-10004")
    }
    assert statuses == {"PAID_UNFULFILLED", "FULFILLING", "SHIPPED", "CANCELLED"}
    assert service.get_order(access(user="user-a2"), "ORD-10005")["order_id"] == "ORD-10005"
    assert service.get_order(access("tenant-b", "user-b1"), "ORD-20001")["order_id"] == "ORD-20001"


def test_查询他人订单不可见_AC_01() -> None:
    with pytest.raises(OrderNotFound):
        oms().get_order(access(), "ORD-10005")


def test_最近订单只返回本人订单_AC_01() -> None:
    orders = oms().list_recent_orders(access(), limit=10)
    assert {order["order_id"] for order in orders} == {
        "ORD-10001",
        "ORD-10002",
        "ORD-10003",
        "ORD-10004",
    }
    assert len(oms().list_recent_orders(access(), limit=2)) == 2


def test_返回值为深拷贝_AC_01() -> None:
    service = oms()
    order = service.get_order(access(), "ORD-10001")
    original = copy.deepcopy(order)
    order["items"].clear()
    assert service.get_order(access(), "ORD-10001") == original


def test_提交取消幂等_AC_09() -> None:
    service = oms()
    first = service.submit_cancel(access(), "ORD-10001", "idem-0001-abcdef")
    second = service.submit_cancel(access(), "ORD-10001", "idem-0001-abcdef")
    assert first == second == "ACCEPTED"


def test_同一幂等键不得用于不同订单_AC_09() -> None:
    service = oms()
    service.submit_cancel(access(), "ORD-10001", "idem-0002-abcdef")
    with pytest.raises(IdempotencyConflict):
        service.submit_cancel(access(), "ORD-10003", "idem-0002-abcdef")


def test_同一订单不得重复受理_AC_09() -> None:
    service = oms()
    service.submit_cancel(access(), "ORD-10001", "idem-0003-abcdef")
    with pytest.raises(CancelRejected):
        service.submit_cancel(access(), "ORD-10001", "idem-0004-abcdef")


def test_跨用户与他人订单不可提交_AC_09() -> None:
    service = oms()
    with pytest.raises(OrderNotFound):
        service.submit_cancel(access(), "ORD-10005", "idem-0005-abcdef")
    with pytest.raises(OrderNotFound):
        service.submit_cancel(access(), "ORD-20001", "idem-0006-abcdef")


def test_已发货订单不可提交_AC_09() -> None:
    with pytest.raises(CancelRejected):
        oms().submit_cancel(access(), "ORD-10003", "idem-0007-abcdef")


def test_按幂等键查询结果且按租户隔离_AC_10() -> None:
    service = oms()
    service.submit_cancel(access(), "ORD-10001", "idem-0008-abcdef")
    assert service.get_cancel_result("tenant-a", "idem-0008-abcdef") == "ACCEPTED"
    with pytest.raises(OrderNotFound):
        service.get_cancel_result("tenant-b", "idem-0008-abcdef")
    with pytest.raises(OrderNotFound):
        service.get_cancel_result("tenant-a", "idem-unknown")


def test_取消结果可推进到四态_AC_10() -> None:
    service = oms()
    service.submit_cancel(access(), "ORD-10001", "idem-0009-abcdef")
    for state in ("CANCELLED", "REJECTED", "UNKNOWN"):
        service.set_cancel_result("tenant-a", "idem-0009-abcdef", state)
        assert service.get_cancel_result("tenant-a", "idem-0009-abcdef") == state


def test_归属由夹具判定_AC_01() -> None:
    service = oms()
    assert service.is_visible(access(), "ORD-10001") is True
    assert service.is_visible(access(), "ORD-10005") is False
    assert service.is_visible(access("tenant-b", "user-b1"), "ORD-20001") is True


def test_匿名会话凭已校验订单可见_基座豁免() -> None:
    service = oms()
    anonymous = OmsAccess(tenant_id="tenant-a", verified_order_ids=frozenset({"ORD-10005"}))

    assert service.is_visible(anonymous, "ORD-10005") is True
    assert service.is_visible(anonymous, "ORD-10001") is False


def test_小数秒时间排序正确_AC_01(tmp_path) -> None:
    import json

    base = {
        "item_summary": "耳机 × 1",
        "order_status": "PAID_UNFULFILLED",
        "cancelable": True,
        "amount_cents": 100,
        "currency": "CNY",
        "items": [{"sku": "S", "name": "耳机", "quantity": 1, "unit_amount_cents": 100}],
        "paid_at": "2026-11-10T00:00:00Z",
        "shipped_at": None,
    }
    entries = [
        {
            "tenant_id": "tenant-a",
            "user_id": "user-a1",
            "order": {**base, "order_id": "ORD-A", "created_at": "2026-11-10T02:00:00.500Z"},
        },
        {
            "tenant_id": "tenant-a",
            "user_id": "user-a1",
            "order": {**base, "order_id": "ORD-B", "created_at": "2026-11-10T02:00:00Z"},
        },
    ]
    path = tmp_path / "orders.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    service = MockOmsAdapter(fixtures_path=path)
    orders = service.list_recent_orders(access(), limit=10)
    assert [order["order_id"] for order in orders] == ["ORD-A", "ORD-B"]
