"""OmsPort 共用契约测试骨架；T-25 接入 Http 后升级为 AC-25。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest

from services.adapters.oms.faults import FaultRule
from services.adapters.oms.mock import MockOmsAdapter
from services.adapters.oms.port import OmsAccess, OmsPort
from services.errors import DownstreamInvalidResponse, IdempotencyConflict, OrderNotFound

ACCESS = OmsAccess(tenant_id="tenant-a", user_id="user-a1")
KEY = "idem-contract-0001"


@dataclass(frozen=True)
class Harness:
    name: str
    build: Callable[[], OmsPort]
    make_timeout: Callable[[OmsPort], None]
    make_invalid: Callable[[OmsPort], None]
    make_unknown: Callable[[OmsPort], None]


def _mock_timeout(adapter: OmsPort) -> None:
    cast(MockOmsAdapter, adapter).faults.add(FaultRule(kind="timeout", tool="get_order"))


def _mock_invalid(adapter: OmsPort) -> None:
    cast(MockOmsAdapter, adapter).faults.add(FaultRule(kind="invalid_response", tool="get_order"))


def _mock_unknown(adapter: OmsPort) -> None:
    mock = cast(MockOmsAdapter, adapter)
    mock.submit_cancel(ACCESS, "ORD-10001", KEY)
    mock.set_cancel_result("tenant-a", KEY, "UNKNOWN")


MOCK = Harness(
    name="mock",
    build=MockOmsAdapter,
    make_timeout=_mock_timeout,
    make_invalid=_mock_invalid,
    make_unknown=_mock_unknown,
)

HARNESSES = [pytest.param(MOCK, id="mock")]


@pytest.fixture(params=HARNESSES)
def harness(request: pytest.FixtureRequest) -> Harness:
    return cast(Harness, request.param)


def test_get_order_returns_contract_shape(harness: Harness) -> None:
    order = harness.build().get_order(ACCESS, "ORD-10001")

    assert order["order_id"] == "ORD-10001"
    assert order["order_status"] == "PAID_UNFULFILLED"


def test_list_limit_zero_returns_empty(harness: Harness) -> None:
    assert harness.build().list_recent_orders(ACCESS, 0) == []


def test_unauthorized_order_is_invisible(harness: Harness) -> None:
    adapter = harness.build()

    assert adapter.is_visible(ACCESS, "ORD-10005") is False
    with pytest.raises(OrderNotFound):
        adapter.get_order(ACCESS, "ORD-10005")


def test_timeout_maps_to_timeout_error(harness: Harness) -> None:
    adapter = harness.build()
    harness.make_timeout(adapter)

    with pytest.raises(TimeoutError):
        adapter.get_order(ACCESS, "ORD-10001")


def test_invalid_response_maps_to_downstream_error(harness: Harness) -> None:
    adapter = harness.build()
    harness.make_invalid(adapter)

    with pytest.raises(DownstreamInvalidResponse):
        adapter.get_order(ACCESS, "ORD-10001")


def test_unknown_cancel_result_is_returned(harness: Harness) -> None:
    adapter = harness.build()
    harness.make_unknown(adapter)

    assert adapter.get_cancel_result("tenant-a", KEY) == "UNKNOWN"


def test_duplicate_idempotency_key_returns_same_state(harness: Harness) -> None:
    adapter = harness.build()

    first = adapter.submit_cancel(ACCESS, "ORD-10001", KEY)
    second = adapter.submit_cancel(ACCESS, "ORD-10001", KEY)

    assert first == second == "ACCEPTED"


def test_idempotency_key_reuse_across_orders_conflicts(harness: Harness) -> None:
    adapter = harness.build()
    adapter.submit_cancel(ACCESS, "ORD-10001", KEY)

    with pytest.raises(IdempotencyConflict):
        adapter.submit_cancel(ACCESS, "ORD-10003", KEY)
