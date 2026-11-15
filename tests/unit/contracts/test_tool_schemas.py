"""Tool 契约：统一错误封套、请求响应正反例、错误码覆盖。

覆盖 AC-01、AC-04、AC-05、AC-09、AC-10、AC-11。
"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from services.api.domain.cancellation import CancellationState
from services.api.domain.errors import ErrorCode, error_spec

SCHEMA_DIR = Path("packages/contracts/schemas")
TOOLS_DIR = Path("packages/contracts/tools")
DOMAIN = json.loads((SCHEMA_DIR / "domain.json").read_text(encoding="utf-8"))

TOOL_NAMES = (
    "list_recent_orders",
    "get_order",
    "get_cancel_eligibility",
    "submit_cancel",
    "get_cancel_result",
)


def load_tool(name: str) -> dict[str, Any]:
    return json.loads((TOOLS_DIR / f"{name}.json").read_text(encoding="utf-8"))


def registry() -> Registry:
    resources = [(DOMAIN["$id"], Resource.from_contents(DOMAIN))]
    for name in TOOL_NAMES:
        doc = load_tool(name)
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def validate_doc(doc: dict[str, Any], def_name: str, instance: Any) -> None:
    """在整份文档内解析 $ref，只校验指定的 $defs 条目。"""
    validator = Draft202012Validator(doc, registry=registry())
    errors = list(validator.descend(instance, {"$ref": f"{doc['$id']}#/$defs/{def_name}"}))
    if errors:
        raise AssertionError("；".join(error.message for error in errors[:3]))


def summary_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "order_id": "ORD-10001",
        "item_summary": "无线耳机 × 1",
        "order_status": "PAID_UNFULFILLED",
        "cancelable": True,
        "amount_cents": 39900,
        "currency": "CNY",
        "created_at": "2026-11-14T06:02:00Z",
    }
    data.update(overrides)
    return data


def detail_payload(**overrides: Any) -> dict[str, Any]:
    data = summary_payload()
    data.update(
        items=[{"sku": "SKU-1", "name": "无线耳机", "quantity": 1, "unit_amount_cents": 39900}],
        paid_at="2026-11-14T06:01:00Z",
        shipped_at=None,
    )
    data.update(overrides)
    return data


def test_每个Tool都有契约与错误码声明_AC_04() -> None:
    for name in TOOL_NAMES:
        doc = load_tool(name)
        assert doc["title"] == name
        assert "Request" in doc["$defs"] and "Response" in doc["$defs"]
        codes = doc["x-error-codes"]
        assert codes, f"{name} 未声明错误码"
        assert set(codes) <= {code.value for code in ErrorCode}


def test_全部错误码都被至少一个Tool声明_AC_11() -> None:
    declared: set[str] = set()
    for name in TOOL_NAMES:
        declared |= set(load_tool(name)["x-error-codes"])
    assert declared == {code.value for code in ErrorCode}


def test_统一错误封套可用_AC_11() -> None:
    envelope = {"code": "DEPENDENCY_TIMEOUT", "retryable": True, "visible": True, "message": "超时"}
    validate_doc(DOMAIN, "ErrorEnvelope", envelope)


@pytest.mark.parametrize(
    "overrides",
    [
        {"code": "UNKNOWN"},
        {"retryable": "true"},
        {"message": ""},
        {"extra": "x"},
    ],
)
def test_错误封套拒绝非法输入_AC_11(overrides: dict[str, Any]) -> None:
    envelope = {"code": "DEPENDENCY_TIMEOUT", "retryable": True, "visible": True, "message": "超时"}
    envelope.update(overrides)
    with pytest.raises(AssertionError):
        validate_doc(DOMAIN, "ErrorEnvelope", envelope)


def test_封套属性与错误码规格一致_AC_11() -> None:
    for code in ErrorCode:
        spec = error_spec(code)
        envelope = {
            "code": code.value,
            "retryable": spec.retryable,
            "visible": spec.visible,
            "message": spec.user_message,
        }
        validate_doc(DOMAIN, "ErrorEnvelope", envelope)


def test_get_order请求与响应_AC_01() -> None:
    doc = load_tool("get_order")
    validate_doc(doc, "Request", {"order_id": "ORD-10001"})
    validate_doc(doc, "Response", detail_payload())
    with pytest.raises(AssertionError):
        validate_doc(doc, "Request", {"order_id": ""})
    with pytest.raises(AssertionError):
        validate_doc(doc, "Response", detail_payload(order_status="UNKNOWN"))


def test_list_recent_orders请求与响应_AC_01() -> None:
    doc = load_tool("list_recent_orders")
    validate_doc(doc, "Request", {"limit": 5})
    validate_doc(doc, "Response", [summary_payload()])
    with pytest.raises(AssertionError):
        validate_doc(doc, "Request", {"limit": 0})
    with pytest.raises(AssertionError):
        validate_doc(doc, "Response", [{"order_id": "x"}])


def test_get_cancel_eligibility请求与响应_AC_04() -> None:
    doc = load_tool("get_cancel_eligibility")
    validate_doc(doc, "Request", {"order_id": "ORD-10001"})
    validate_doc(
        doc,
        "Response",
        {"eligible": True, "reason_code": "UNFULFILLED", "requires_confirmation": True},
    )
    with pytest.raises(AssertionError):
        validate_doc(doc, "Request", {"order_id": 1})


def test_submit_cancel请求与响应_AC_05() -> None:
    doc = load_tool("submit_cancel")
    validate_doc(doc, "Request", {"order_id": "ORD-10001", "idempotency_key": "idem-0001-abcdef"})
    validate_doc(doc, "Response", {"state": CancellationState.SUBMIT_UNKNOWN.value})
    with pytest.raises(AssertionError):
        validate_doc(doc, "Request", {"order_id": "ORD-10001"})
    with pytest.raises(AssertionError):
        validate_doc(doc, "Response", {"state": "NOT_A_STATE"})


def test_get_cancel_result请求与响应_AC_10() -> None:
    doc = load_tool("get_cancel_result")
    validate_doc(doc, "Request", {"idempotency_key": "idem-0001-abcdef"})
    validate_doc(doc, "Response", {"state": CancellationState.ACCEPTED.value})
    with pytest.raises(AssertionError):
        validate_doc(doc, "Response", {"state": 1})
