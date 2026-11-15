"""查询 Tool：网关调用、归属与错误映射（AC-01、AC-02、AC-03）。"""

import pytest

from services.api.auth import Identity
from services.api.domain.errors import ErrorCode
from services.mock_oms.faults import FaultRule
from services.mock_oms.service import MockOms
from services.tools.gateway import GatewayError
from services.tools.query import build_query_gateway

OWNER = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
OTHER_TENANT = Identity("wang-qiang", "user-b1", "tenant-b", "王强", "示例商户 B")


def gateway(oms: MockOms):
    return build_query_gateway(oms)


def test_查询本人订单_AC_01() -> None:
    result = gateway(MockOms()).invoke(
        "get_order", {"order_id": "ORD-10001"}, OWNER, trace_id="t-1"
    )
    assert result["order_id"] == "ORD-10001"
    assert result["order_status"] == "PAID_UNFULFILLED"


def test_查询他人订单返回统一错误_AC_02() -> None:
    with pytest.raises(GatewayError) as exc:
        gateway(MockOms()).invoke("get_order", {"order_id": "ORD-10005"}, OWNER, trace_id="t-1")
    assert exc.value.status_code == 404
    assert exc.value.payload["code"] == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value


def test_跨租户查询被拒绝_AC_03() -> None:
    with pytest.raises(GatewayError) as exc:
        gateway(MockOms()).invoke(
            "get_order", {"order_id": "ORD-10001"}, OTHER_TENANT, trace_id="t-1"
        )
    assert exc.value.payload["code"] == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value


def test_最近订单倒序且受limit约束_AC_01() -> None:
    result = gateway(MockOms()).invoke("list_recent_orders", {"limit": 2}, OWNER, trace_id="t-1")
    assert len(result) == 2
    assert [item["order_id"] for item in result] == ["ORD-10002", "ORD-10001"]


def test_故障注入经网关归一_AC_01() -> None:
    oms = MockOms()
    oms.faults.add(FaultRule(kind="timeout", tool="get_order"))
    with pytest.raises(GatewayError) as exc:
        gateway(oms).invoke("get_order", {"order_id": "ORD-10001"}, OWNER, trace_id="t-1")
    assert exc.value.payload["code"] == ErrorCode.DEPENDENCY_UNAVAILABLE.value
