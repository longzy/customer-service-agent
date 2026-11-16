"""Mock OMS Adapter：进程内订单服务，数据来自 JSON 夹具。

写接口必须携带访问上下文：幂等键以 (tenant_id, idempotency_key) 为唯一键。
"""

import copy
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from services.adapters.oms.faults import FaultEngine
from services.adapters.oms.port import OmsAccess
from services.contracts import build_registry, load_domain, validator_for
from services.errors import (
    CancelRejected,
    DownstreamInvalidResponse,
    IdempotencyConflict,
    OrderNotFound,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "orders.json"

SUBMITTABLE = {"PAID_UNFULFILLED"}
OMS_STATES = {"ACCEPTED", "CANCELLED", "REJECTED", "UNKNOWN"}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MockOmsAdapter:
    """订单查询与取消提交。数据只读加载，取消结果保存在进程内。"""

    def __init__(self, fixtures_path: Path | None = None) -> None:
        domain = load_domain()
        registry = build_registry(domain, {})
        self._validator = validator_for(domain, "OrderDetail", registry)
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
        self.calls = {
            "get_order": 0,
            "list_recent_orders": 0,
            "submit_cancel": 0,
            "get_cancel_result": 0,
        }
        self._cancel_results: dict[tuple[str, str], tuple[str, str]] = {}
        self._accepted_orders: dict[str, str] = {}
        self.faults = FaultEngine()

    def _owns(self, order_id: str, access: OmsAccess) -> bool:
        owner = self._owners.get(order_id)
        if owner is None or owner[0] != access.tenant_id:
            return False
        if access.user_id is not None:
            return owner[1] == access.user_id
        return order_id in access.verified_order_ids

    def is_visible(self, access: OmsAccess, order_id: str) -> bool:
        return self._owns(order_id, access)

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

    def get_order(self, access: OmsAccess, order_id: str) -> dict[str, Any]:
        self.calls["get_order"] += 1
        if self._inject("get_order", order_id) == "lost_response":
            raise TimeoutError("get_order")
        if not self._owns(order_id, access):
            raise OrderNotFound(order_id)
        return copy.deepcopy(self._orders[order_id])

    def list_recent_orders(self, access: OmsAccess, limit: int = 5) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit 不能为负")
        self.calls["list_recent_orders"] += 1
        if self._inject("list_recent_orders") == "lost_response":
            raise TimeoutError("list_recent_orders")
        owned = [order for order_id, order in self._orders.items() if self._owns(order_id, access)]
        owned.sort(key=lambda order: _parse_time(order["created_at"]), reverse=True)
        return [copy.deepcopy(order) for order in owned[:limit]]

    def submit_cancel(self, access: OmsAccess, order_id: str, idempotency_key: str) -> str:
        self.calls["submit_cancel"] += 1
        if not self._owns(order_id, access):
            raise OrderNotFound(order_id)
        key = (access.tenant_id, idempotency_key)
        existing = self._cancel_results.get(key)
        if existing is not None:
            if existing[0] != order_id:
                raise IdempotencyConflict(idempotency_key)
            return existing[1]

        kind = self._inject("submit_cancel", order_id)
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
        self.calls["get_cancel_result"] += 1
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
