"""取消资格判定（AC-04、AC-07）。"""

import inspect

import pytest

from services.domain.orders import OrderSummary
from services.errors import DownstreamInvalidResponse
from services.tools import policy
from services.tools.policy import evaluate_eligibility


def order(status: str, cancelable: bool = True) -> OrderSummary:
    return OrderSummary.model_validate(
        {
            "order_id": "ORD-10001",
            "item_summary": "无线耳机 × 1",
            "order_status": status,
            "cancelable": cancelable,
            "amount_cents": 39900,
            "currency": "CNY",
            "created_at": "2026-11-10T02:00:00Z",
        }
    )


def test_未发货订单可取消并要求确认_AC_04() -> None:
    result = evaluate_eligibility(order("PAID_UNFULFILLED"))
    assert result.eligible is True
    assert result.reason_code.value == "UNFULFILLED"
    assert result.requires_confirmation is True


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("FULFILLING", "FULFILLING"),
        ("SHIPPED", "SHIPPED"),
        ("DELIVERED", "DELIVERED"),
        ("CANCELLED", "CANCELLED"),
    ],
)
def test_不可取消状态返回原因码_AC_07(status: str, reason: str) -> None:
    result = evaluate_eligibility(order(status, cancelable=False))
    assert result.eligible is False
    assert result.reason_code.value == reason
    assert result.requires_confirmation is False


def test_契约拒绝不一致的cancelable_基座豁免() -> None:
    with pytest.raises(ValueError):
        order("SHIPPED", cancelable=True)


def test_策略不依赖OMS_基座豁免() -> None:
    assert "mock_oms" not in inspect.getsource(policy)


def test_未知状态无法通过领域模型_基座豁免() -> None:
    with pytest.raises(ValueError):
        order("UNKNOWN")


def test_未知状态在策略层归类为下游异常_基座豁免() -> None:
    class Fake:
        order_status = "UNKNOWN"

    with pytest.raises(DownstreamInvalidResponse):
        evaluate_eligibility(Fake())  # type: ignore[arg-type]
