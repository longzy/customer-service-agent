"""Mock OMS：夹具、读写与幂等（AC-01、AC-05、AC-09）。"""

import pytest

from services.mock_oms.service import MockOms, OrderNotFound


def oms() -> MockOms:
    return MockOms()


def test_夹具覆盖两租户四种状态与跨用户订单_AC_01() -> None:
    service = oms()
    statuses = {
        service.get_order("tenant-a", "user-a1", oid)["order_status"]
        for oid in ("ORD-10001", "ORD-10002", "ORD-10003", "ORD-10004")
    }
    assert statuses == {"PAID_UNFULFILLED", "FULFILLING", "SHIPPED", "CANCELLED"}
    assert service.get_order("tenant-a", "user-a2", "ORD-10005")["order_id"] == "ORD-10005"
    assert service.get_order("tenant-b", "user-b1", "ORD-20001")["order_id"] == "ORD-20001"


def test_查询他人订单不可见_AC_02() -> None:
    with pytest.raises(OrderNotFound):
        oms().get_order("tenant-a", "user-a1", "ORD-10005")


def test_最近订单只返回本人订单_AC_01() -> None:
    orders = oms().list_recent_orders("tenant-a", "user-a1", limit=10)
    assert {order["order_id"] for order in orders} == {
        "ORD-10001",
        "ORD-10002",
        "ORD-10003",
        "ORD-10004",
    }
    assert len(oms().list_recent_orders("tenant-a", "user-a1", limit=2)) == 2


def test_提交取消幂等_AC_09() -> None:
    service = oms()
    first = service.submit_cancel("ORD-10001", "idem-0001-abcdef")
    second = service.submit_cancel("ORD-10001", "idem-0001-abcdef")
    assert first == second == "ACCEPTED"


def test_按幂等键查询结果_AC_10() -> None:
    service = oms()
    service.submit_cancel("ORD-10001", "idem-0002-abcdef")
    assert service.get_cancel_result("idem-0002-abcdef") == "ACCEPTED"
    with pytest.raises(OrderNotFound):
        service.get_cancel_result("idem-unknown")


def test_已发货订单不可提交_AC_05() -> None:
    with pytest.raises(OrderNotFound):
        oms().submit_cancel("ORD-10003", "idem-0003-abcdef")


def test_归属索引由夹具生成_AC_02() -> None:
    service = oms()
    assert service.owns("ORD-10001", "tenant-a", "user-a1") is True
    assert service.owns("ORD-10001", "tenant-a", "user-a2") is False
    assert service.owns("ORD-10001", "tenant-b", "user-b1") is False
