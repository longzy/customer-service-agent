"""AC-25：Mock 与 Http Adapter 的 OmsPort 契约等价。"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from services.adapters.oms.faults import FaultRule
from services.adapters.oms.http import HttpOmsAdapter
from services.adapters.oms.mock import MockOmsAdapter
from services.adapters.oms.port import OmsAccess, OmsPort
from services.errors import DownstreamInvalidResponse, IdempotencyConflict, OrderNotFound

ACCESS = OmsAccess(tenant_id="tenant-a", user_id="user-a1")
KEY = "idem-contract-0001"
FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "adapters"
    / "oms"
    / "fixtures"
    / "orders.json"
)


@dataclass(frozen=True)
class Harness:
    name: str
    build: Callable[[], OmsPort]
    make_timeout: Callable[[OmsPort], None]
    make_connect: Callable[[OmsPort], None]
    make_invalid: Callable[[OmsPort], None]
    make_unknown: Callable[[OmsPort], None]


def _mock_timeout(adapter: OmsPort) -> None:
    cast(MockOmsAdapter, adapter).faults.add(FaultRule(kind="timeout", tool="get_order"))


def _mock_connect(adapter: OmsPort) -> None:
    cast(MockOmsAdapter, adapter).faults.add(FaultRule(kind="unavailable", tool="get_order"))


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
    make_connect=_mock_connect,
    make_invalid=_mock_invalid,
    make_unknown=_mock_unknown,
)


@dataclass
class HttpState:
    timeout: bool = False
    connect: bool = False
    invalid: bool = False
    cancel_states: dict[str, str] = field(default_factory=dict)
    cancel_orders: dict[str, str] = field(default_factory=dict)


def _fixture_order(order_id: str) -> dict[str, Any]:
    entries = json.loads(FIXTURES.read_text(encoding="utf-8"))
    for entry in entries:
        if entry["order"]["order_id"] == order_id:
            return cast(dict[str, Any], entry["order"])
    raise KeyError(order_id)


def _http_handler(state: HttpState) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if state.timeout and path == "/orders/ORD-10001" and request.method == "GET":
            state.timeout = False
            raise httpx.ReadTimeout("timeout", request=request)
        if state.connect and path == "/orders/ORD-10001" and request.method == "GET":
            state.connect = False
            raise httpx.ConnectError("down", request=request)
        if state.invalid and path == "/orders/ORD-10001" and request.method == "GET":
            state.invalid = False
            return httpx.Response(200, text="not-json")
        if path.endswith("/visibility"):
            order_id = path.split("/")[2]
            return httpx.Response(200, json={"visible": order_id != "ORD-10005"})
        if path == "/orders" and request.method == "GET":
            return httpx.Response(200, json=[])
        if path.startswith("/orders/") and request.method == "GET":
            order_id = path.split("/")[2]
            if order_id == "ORD-10005":
                return httpx.Response(404)
            return httpx.Response(200, json=_fixture_order(order_id))
        if path.startswith("/orders/") and path.endswith("/cancellations"):
            order_id = path.split("/")[2]
            payload = json.loads(request.content)
            key = str(payload["idempotency_key"])
            existing = state.cancel_orders.get(key)
            if existing is not None and existing != order_id:
                return httpx.Response(409, json={"detail": "conflict"})
            state.cancel_orders[key] = order_id
            state.cancel_states.setdefault(key, "ACCEPTED")
            return httpx.Response(200, json={"state": state.cancel_states[key]})
        if path.startswith("/cancellations/"):
            key = path.split("/")[2]
            return httpx.Response(200, json={"state": state.cancel_states.get(key, "UNKNOWN")})
        return httpx.Response(404)

    return handler


def _http_harness() -> Harness:
    state = HttpState()

    def build() -> HttpOmsAdapter:
        client = httpx.Client(
            transport=httpx.MockTransport(_http_handler(state)),
            base_url="http://oms.test",
        )
        return HttpOmsAdapter("http://oms.test", client=client)

    def timeout(adapter: OmsPort) -> None:
        state.timeout = True

    def connect(adapter: OmsPort) -> None:
        state.connect = True

    def invalid(adapter: OmsPort) -> None:
        state.invalid = True

    def unknown(adapter: OmsPort) -> None:
        adapter.submit_cancel(ACCESS, "ORD-10001", KEY)
        state.cancel_states[KEY] = "UNKNOWN"

    return Harness(
        name="http",
        build=build,
        make_timeout=timeout,
        make_connect=connect,
        make_invalid=invalid,
        make_unknown=unknown,
    )


def _mock_harness() -> Harness:
    return MOCK


HARNESSES = [pytest.param(_mock_harness, id="mock"), pytest.param(_http_harness, id="http")]


@pytest.fixture(params=HARNESSES)
def harness(request: pytest.FixtureRequest) -> Harness:
    factory = cast(Callable[[], Harness], request.param)
    return factory()


def test_get_order_returns_contract_shape_AC_25(harness: Harness) -> None:
    order = harness.build().get_order(ACCESS, "ORD-10001")

    assert order["order_id"] == "ORD-10001"
    assert order["order_status"] == "PAID_UNFULFILLED"


def test_list_limit_zero_returns_empty_AC_25(harness: Harness) -> None:
    assert harness.build().list_recent_orders(ACCESS, 0) == []


def test_unauthorized_order_is_invisible_AC_25(harness: Harness) -> None:
    adapter = harness.build()

    assert adapter.is_visible(ACCESS, "ORD-10005") is False
    with pytest.raises(OrderNotFound):
        adapter.get_order(ACCESS, "ORD-10005")


def test_timeout_maps_to_timeout_error_AC_25(harness: Harness) -> None:
    adapter = harness.build()
    harness.make_timeout(adapter)

    with pytest.raises(TimeoutError):
        adapter.get_order(ACCESS, "ORD-10001")


def test_connect_error_maps_to_connection_error_AC_25(harness: Harness) -> None:
    adapter = harness.build()
    harness.make_connect(adapter)

    with pytest.raises(ConnectionError):
        adapter.get_order(ACCESS, "ORD-10001")


def test_invalid_response_maps_to_downstream_error_AC_25(harness: Harness) -> None:
    adapter = harness.build()
    harness.make_invalid(adapter)

    with pytest.raises(DownstreamInvalidResponse):
        adapter.get_order(ACCESS, "ORD-10001")


def test_unknown_cancel_result_is_returned_AC_25(harness: Harness) -> None:
    adapter = harness.build()
    harness.make_unknown(adapter)

    assert adapter.get_cancel_result("tenant-a", KEY) == "UNKNOWN"


def test_duplicate_idempotency_key_returns_same_state_AC_25(harness: Harness) -> None:
    adapter = harness.build()

    first = adapter.submit_cancel(ACCESS, "ORD-10001", KEY)
    second = adapter.submit_cancel(ACCESS, "ORD-10001", KEY)

    assert first == second == "ACCEPTED"


def test_idempotency_key_reuse_across_orders_conflicts_AC_25(harness: Harness) -> None:
    adapter = harness.build()
    adapter.submit_cancel(ACCESS, "ORD-10001", KEY)

    with pytest.raises(IdempotencyConflict):
        adapter.submit_cancel(ACCESS, "ORD-10003", KEY)
