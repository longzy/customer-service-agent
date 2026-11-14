"""契约正反例：JSON Schema 必须能接受合法数据、拒绝非法数据。"""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from services.api.domain.cancellation import CancellationState
from services.api.domain.errors import ErrorCode
from services.api.domain.orders import OrderStatus

SCHEMA_PATH = Path("packages/contracts/schemas/domain.json")
DOCUMENT = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


_VALIDATOR = Draft202012Validator(DOCUMENT)


def validate(def_name: str, instance: Any) -> None:
    """在整份文档内解析 $ref，只校验指定的 $defs 条目。"""
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


def test_合法订单摘要通过() -> None:
    validate("OrderSummary", order_payload())


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount_cents": -1},
        {"currency": "cny"},
        {"order_status": "UNKNOWN"},
        {"order_id": ""},
    ],
)
def test_非法订单摘要被拒绝(overrides: dict[str, Any]) -> None:
    with pytest.raises(AssertionError):
        validate("OrderSummary", order_payload(**overrides))


def test_合法订单详情通过() -> None:
    detail = order_payload(
        items=[{"sku": "SKU-1", "name": "无线耳机", "quantity": 1, "unit_amount_cents": 39900}]
    )
    validate("OrderDetail", detail)


def test_订单详情缺商品明细被拒绝() -> None:
    with pytest.raises(AssertionError):
        validate("OrderDetail", order_payload())


def test_订单详情包含订单摘要的全部必填字段() -> None:
    summary_required = set(DOCUMENT["$defs"]["OrderSummary"]["required"])
    detail_required = set(DOCUMENT["$defs"]["OrderDetail"]["required"])
    assert summary_required <= detail_required


def test_合法资格结果通过() -> None:
    validate(
        "CancelEligibility",
        {"eligible": True, "reason_code": "UNFULFILLED", "requires_confirmation": True},
    )


def test_资格结果缺字段被拒绝() -> None:
    with pytest.raises(AssertionError):
        validate("CancelEligibility", {"eligible": True})


def test_schema枚举与代码枚举一致() -> None:
    assert sorted(DOCUMENT["$defs"]["OrderStatus"]["enum"]) == sorted(s.value for s in OrderStatus)
    assert sorted(DOCUMENT["$defs"]["CancellationState"]["enum"]) == sorted(
        s.value for s in CancellationState
    )
    assert sorted(DOCUMENT["$defs"]["ErrorCode"]["enum"]) == sorted(c.value for c in ErrorCode)
