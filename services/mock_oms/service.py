"""Mock OMS：进程内订单服务，数据来自 JSON 夹具。

写接口必须携带身份：幂等键以 (tenant_id, idempotency_key) 为唯一键。
"""

import copy
import json
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from services.errors import (
    CancelRejected,
    DownstreamInvalidResponse,
    IdempotencyConflict,
    OrderNotFound,
)
from services.mock_oms.faults import FaultEngine

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "orders.json"

SUBMITTABLE = {"PAID_UNFULFILLED"}
OMS_STATES = {"ACCEPTED", "CANCELLED", "REJECTED", "UNKNOWN"}


class MockOms:
    """订单查询与取消提交。数据只读加载，取消结果保存在进程内。"""

    def __init__(self, fixtures_path: Path | None = None) -> None:
        domain = json.loads((CONTRACTS / "schemas" / "domain.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(domain["$id"], Resource.from_contents(domain))
        self._validator = Draft202012Validator(
            {"$ref": f"{domain['$id']}#/$defs/OrderDetail"}, registry=registry
        )
        entries = json.loads((fixtures_path or FIXTURES).read_text(encoding="utf-8"))
        self._orders: dict[str, dict[str, Any]] = {}
        self._owners: dict[str, tuple[str, str]] = {}
        for entry in entries:
            errors = list(self._validator.iter_errors(entry["order"]))
            if errors:
                raise ValueError(f"夹具非法：{entry['order'].get('order_id')} {errors[0].message}")
            tenant_id, user_id = entry["tenant_id"], entry["user_id"]
            if not tenant_id or not user_id:
                raise ValueError("夹具条目必须包含 tenant_id 与 user_id")
            order_id = entry["order"]["order_id"]
            if order_id in self._orders:
                raise ValueError(f"夹具订单号重复：{order_id}")
            self._orders[order_id] = entry["order"]
            self._owners[order_id] = (tenant_id, user_id)
        self._cancel_results: dict[tuple[str, str], tuple[str, str]] = {}
        self._accepted_orders: dict[str, str] = {}
        self.faults = FaultEngine()

    def owns(self, order_id: str, tenant_id: str, user_id: str) -> bool:
        return self._owners.get(order_id) == (tenant_id, user_id)

    def build_ownership_index(self, index: Any) -> None:
        """把夹具中的归属写入网关使用的索引，保证只有一份真相。"""
        for order_id, (tenant_id, user_id) in self._owners.items():
            index.register(order_id, tenant_id, user_id)

    def _inject(self, tool: str, order_id: str | None = None) -> str | None:
        kind = self.faults.take(tool, order_id)
        if kind == "delay":
            time.sleep(self.faults.take_delay_seconds)
        elif kind == "timeout":
            raise TimeoutError(tool)
        elif kind == "unavailable":
            raise ConnectionError(tool)
        elif kind == "invalid_response":
            raise DownstreamInvalidResponse(tool)
        return kind

    def get_order(self, tenant_id: str, user_id: str, order_id: str) -> dict[str, Any]:
        if self._inject("get_order", order_id) == "lost_response":
            raise TimeoutError("get_order")
        if not self.owns(order_id, tenant_id, user_id):
            raise OrderNotFound(order_id)
        return copy.deepcopy(self._orders[order_id])

    def list_recent_orders(
        self, tenant_id: str, user_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        if self._inject("list_recent_orders") == "lost_response":
            raise TimeoutError("list_recent_orders")
        owned = [
            order
            for order_id, order in self._orders.items()
            if self.owns(order_id, tenant_id, user_id)
        ]
        owned.sort(key=lambda order: order["created_at"], reverse=True)
        return [copy.deepcopy(order) for order in owned[:limit]]

    def submit_cancel(
        self, tenant_id: str, user_id: str, order_id: str, idempotency_key: str
    ) -> str:
        key = (tenant_id, idempotency_key)
        existing = self._cancel_results.get(key)
        if existing is not None:
            if existing[0] != order_id:
                raise IdempotencyConflict(idempotency_key)
            return existing[1]

        kind = self._inject("submit_cancel", order_id)
        if not self.owns(order_id, tenant_id, user_id):
            raise OrderNotFound(order_id)
        if order_id in self._accepted_orders:
            raise CancelRejected("已受理，等待结果")
        order = self._orders[order_id]
        if order["order_status"] not in SUBMITTABLE:
            raise CancelRejected(order["order_status"])

        self._cancel_results[key] = (order_id, "ACCEPTED")
        self._accepted_orders[order_id] = idempotency_key
        if kind == "lost_response":
            raise TimeoutError("lost_response")
        return "ACCEPTED"

    def get_cancel_result(self, tenant_id: str, idempotency_key: str) -> str:
        if self._inject("get_cancel_result") == "lost_response":
            raise TimeoutError("get_cancel_result")
        result = self._cancel_results.get((tenant_id, idempotency_key))
        if result is None:
            raise OrderNotFound(idempotency_key)
        return result[1]

    def set_cancel_result(self, tenant_id: str, idempotency_key: str, state: str) -> None:
        """测试与管理接口使用：把结果推进到 ACCEPTED/CANCELLED/REJECTED/UNKNOWN。"""
        if state not in OMS_STATES:
            raise ValueError(f"未知状态：{state}")
        key = (tenant_id, idempotency_key)
        if key not in self._cancel_results:
            raise OrderNotFound(idempotency_key)
        order_id, _ = self._cancel_results[key]
        self._cancel_results[key] = (order_id, state)
