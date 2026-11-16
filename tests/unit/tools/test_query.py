"""查询 Tool：契约响应、归属、审计与错误映射（AC-01、AC-02、AC-03）。"""

from typing import Any

import pytest

from services.contracts import build_registry, load_domain, load_tool_documents, validator_for
from services.domain.errors import ErrorCode
from services.identity import Identity
from services.mock_oms.faults import FaultRule
from services.mock_oms.service import MockOms
from services.tools.gateway import GatewayError, ToolGateway
from services.tools.query import SUMMARY_FIELDS, build_query_gateway

OWNER = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
SAME_TENANT = Identity("li-hua", "user-a2", "tenant-a", "李华", "示例商户 A")
OTHER_TENANT = Identity("wang-qiang", "user-b1", "tenant-b", "王强", "示例商户 B")


def gateway(oms: MockOms, audit: Any = None) -> ToolGateway:
    return build_query_gateway(oms, audit=audit)


def response_validator(tool: str):
    domain = load_domain()
    documents = load_tool_documents()
    registry = build_registry(domain, documents)
    return validator_for(documents[tool], "Response", registry)


def test_查询本人订单_AC_01() -> None:
    result = gateway(MockOms()).invoke(
        "get_order", {"order_id": "ORD-10001"}, OWNER, trace_id="t-1"
    )
    assert result["order_id"] == "ORD-10001"
    assert result["order_status"] == "PAID_UNFULFILLED"
    assert response_validator("get_order").is_valid(result)


def test_最近订单输出符合摘要契约_AC_01() -> None:
    result = gateway(MockOms()).invoke("list_recent_orders", {"limit": 10}, OWNER, trace_id="t-1")
    assert all(set(item) == set(SUMMARY_FIELDS) for item in result)
    assert response_validator("list_recent_orders").is_valid(result)


def test_最近订单倒序且受limit约束_AC_01() -> None:
    result = gateway(MockOms()).invoke("list_recent_orders", {"limit": 2}, OWNER, trace_id="t-1")
    assert [item["order_id"] for item in result] == ["ORD-10002", "ORD-10001"]


def test_最近订单按本人与租户过滤_AC_03() -> None:
    service = MockOms()
    other_tenant = gateway(service).invoke(
        "list_recent_orders", {"limit": 10}, OTHER_TENANT, trace_id="t-1"
    )
    assert [item["order_id"] for item in other_tenant] == [
        "ORD-20002",
        "ORD-20001",
        "ORD-20003",
        "ORD-20004",
    ]
    same_tenant = gateway(MockOms()).invoke(
        "list_recent_orders", {"limit": 10}, SAME_TENANT, trace_id="t-1"
    )
    assert [item["order_id"] for item in same_tenant] == ["ORD-10005"]


def test_查询他人订单返回统一错误且不调用OMS_AC_02() -> None:
    service = MockOms()
    with pytest.raises(GatewayError) as exc:
        gateway(service).invoke("get_order", {"order_id": "ORD-10005"}, OWNER, trace_id="t-1")
    assert exc.value.status_code == 404
    assert exc.value.payload["code"] == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value
    assert service.calls["get_order"] == 0, "越权请求不应触达 OMS"


def test_跨租户查询被拒绝且不调用OMS_AC_03() -> None:
    service = MockOms()
    with pytest.raises(GatewayError) as exc:
        gateway(service).invoke(
            "get_order", {"order_id": "ORD-10001"}, OTHER_TENANT, trace_id="t-1"
        )
    assert exc.value.payload["code"] == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value
    assert service.calls["get_order"] == 0


def test_越权拒绝写入审计_AC_02() -> None:
    events: list[dict[str, Any]] = []
    with pytest.raises(GatewayError):
        gateway(MockOms(), audit=events.append).invoke(
            "get_order", {"order_id": "ORD-10005"}, OWNER, trace_id="t-1"
        )
    assert events[-1]["result"] == "rejected"
    assert events[-1]["error_code"] == "NOT_FOUND_OR_UNAUTHORIZED"


@pytest.mark.parametrize(
    ("tool", "kind", "status", "code"),
    [
        ("get_order", "timeout", 504, "DEPENDENCY_UNAVAILABLE"),
        ("get_order", "unavailable", 503, "DEPENDENCY_UNAVAILABLE"),
        ("get_order", "invalid_response", 502, "INVALID_RESPONSE"),
        ("list_recent_orders", "timeout", 504, "DEPENDENCY_TIMEOUT"),
        ("list_recent_orders", "unavailable", 503, "DEPENDENCY_UNAVAILABLE"),
        ("list_recent_orders", "invalid_response", 502, "INVALID_RESPONSE"),
    ],
)
def test_故障经网关映射为契约错误码_基座豁免(tool: str, kind: str, status: int, code: str) -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind=kind, tool=tool))
    payload = {"order_id": "ORD-10001"} if tool == "get_order" else {"limit": 5}
    with pytest.raises(GatewayError) as exc:
        gateway(service).invoke(tool, payload, OWNER, trace_id="t-1")
    assert exc.value.status_code == status
    assert exc.value.payload["code"] == code


def test_延迟故障后正常返回_基座豁免() -> None:
    service = MockOms()
    service.faults.add(FaultRule(kind="delay", tool="get_order", delay_ms=1))
    result = gateway(service).invoke("get_order", {"order_id": "ORD-10001"}, OWNER, trace_id="t-1")
    assert result["order_id"] == "ORD-10001"
