"""契约正反例与 Schema/模型一致性（AC-04、AC-07、AC-11）。"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from services.api.domain.cancellation import CancelEligibility, CancellationState
from services.api.domain.errors import ErrorCode
from services.api.domain.orders import OrderDetail, OrderStatus, OrderSummary

SCHEMA_PATH = Path("packages/contracts/schemas/domain.json")
DOCUMENT = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_VALIDATOR = Draft202012Validator(DOCUMENT)


def validate(def_name: str, instance: Any) -> None:
    errors = list(_VALIDATOR.descend(instance, {"$ref": f"#/$defs/{def_name}"}))
    if errors:
        raise AssertionError("；".join(error.message for error in errors[:3]))


def order_payload(**overrides: Any) -> dict[str, Any]:
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
    data = order_payload()
    data.update(
        items=[{"sku": "SKU-1", "name": "无线耳机", "quantity": 1, "unit_amount_cents": 39900}],
        paid_at="2026-11-14T06:01:00Z",
        shipped_at=None,
    )
    data.update(overrides)
    return data


def test_合法订单摘要通过_AC_04() -> None:
    validate("OrderSummary", order_payload())


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount_cents": -1},
        {"currency": "cny"},
        {"order_status": "UNKNOWN"},
        {"order_id": ""},
        {"created_at": "2026-11-14"},
        {"created_at": "not-a-date"},
        {"created_at": "2026-11-14T14:02:00+08:00"},
        {"unexpected": "x"},
    ],
)
def test_非法订单摘要被拒绝_AC_04(overrides: dict[str, Any]) -> None:
    with pytest.raises(AssertionError):
        validate("OrderSummary", order_payload(**overrides))


def test_已发货订单不得标记可取消_AC_07() -> None:
    with pytest.raises(AssertionError):
        validate("OrderSummary", order_payload(order_status="SHIPPED", cancelable=True))


def test_合法订单详情通过_AC_04() -> None:
    validate("OrderDetail", detail_payload())


def test_订单详情缺商品明细被拒绝_AC_04() -> None:
    data = detail_payload()
    data.pop("items")
    with pytest.raises(AssertionError):
        validate("OrderDetail", data)


def test_订单详情缺时间字段被拒绝_AC_04() -> None:
    data = detail_payload()
    data.pop("paid_at")
    with pytest.raises(AssertionError):
        validate("OrderDetail", data)


def test_合法资格结果通过_AC_04() -> None:
    validate(
        "CancelEligibility",
        {"eligible": True, "reason_code": "UNFULFILLED", "requires_confirmation": True},
    )


def test_资格结果缺字段被拒绝_AC_04() -> None:
    with pytest.raises(AssertionError):
        validate("CancelEligibility", {"eligible": True})


def test枚举与代码一致_AC_11() -> None:
    assert sorted(DOCUMENT["$defs"]["OrderStatus"]["enum"]) == sorted(s.value for s in OrderStatus)
    assert sorted(DOCUMENT["$defs"]["CancellationState"]["enum"]) == sorted(
        s.value for s in CancellationState
    )
    assert sorted(DOCUMENT["$defs"]["ErrorCode"]["enum"]) == sorted(c.value for c in ErrorCode)


def test摘要必填字段与模型一致_AC_04() -> None:
    schema_required = set(DOCUMENT["$defs"]["OrderSummary"]["required"])
    model_required = {
        name for name, field in OrderSummary.model_fields.items() if field.is_required()
    }
    assert schema_required == model_required
    assert set(DOCUMENT["$defs"]["OrderSummary"]["properties"]) == set(
        OrderSummary.model_fields
    )


def test详情必填字段与模型一致_AC_04() -> None:
    schema_required = set(DOCUMENT["$defs"]["OrderDetail"]["required"])
    model_required = {
        name for name, field in OrderDetail.model_fields.items() if field.is_required()
    }
    assert schema_required == model_required


def test资格结果字段与模型一致_AC_04() -> None:
    schema_props = set(DOCUMENT["$defs"]["CancelEligibility"]["properties"])
    assert schema_props == set(CancelEligibility.model_fields)


def test_模型与schema都拒绝额外字段_AC_04() -> None:
    with pytest.raises(ValidationError):
        OrderSummary(**order_payload(unexpected="x"))
    with pytest.raises(AssertionError):
        validate("OrderSummary", order_payload(unexpected="x"))
