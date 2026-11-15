"""Mock OMS：进程内订单服务，数据来自 JSON 夹具。"""

import json
import time
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from services.mock_oms.faults import FaultEngine

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "orders.json"

SUBMITTABLE = {"PAID_UNFULFILLED"}


class OrderNotFound(Exception):
    """订单不存在、不属于当前用户，或不可取消；对外统一表达为“查无此单”。"""


class MockOmsInvalidResponse(Exception):
    """模拟下游返回非法格式，由工具层归类为 INVALID_RESPONSE。"""


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
            order_id = entry["order"]["order_id"]
            self._orders[order_id] = entry["order"]
            self._owners[order_id] = (entry["tenant_id"], entry["user_id"])
        self._cancel_results: dict[str, str] = {}
        self.faults = FaultEngine()

    def _inject(self, tool: str, order_id: str | None = None) -> None:
        kind = self.faults.take(tool, order_id)
        if kind == "delay":
            time.sleep(0.01)
        elif kind == "timeout":
            raise TimeoutError(tool)
        elif kind == "unavailable":
            raise ConnectionError(tool)
        elif kind == "invalid_response":
            raise MockOmsInvalidResponse(tool)

    def owns(self, order_id: str, tenant_id: str, user_id: str) -> bool:
        return self._owners.get(order_id) == (tenant_id, user_id)

    def get_order(self, tenant_id: str, user_id: str, order_id: str) -> dict[str, Any]:
        self._inject("get_order", order_id)
        if not self.owns(order_id, tenant_id, user_id):
            raise OrderNotFound(order_id)
        return dict(self._orders[order_id])

    def list_recent_orders(
        self, tenant_id: str, user_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        self._inject("list_recent_orders")
        owned = [
            order
            for order_id, order in self._orders.items()
            if self.owns(order_id, tenant_id, user_id)
        ]
        owned.sort(key=lambda order: order["created_at"], reverse=True)
        return [dict(order) for order in owned[:limit]]

    def submit_cancel(self, order_id: str, idempotency_key: str) -> str:
        kind = self.faults.take("submit_cancel", order_id)
        if kind == "delay":
            time.sleep(0.01)
        elif kind == "timeout":
            raise TimeoutError("submit_cancel")
        elif kind == "unavailable":
            raise ConnectionError("submit_cancel")
        elif kind == "invalid_response":
            raise MockOmsInvalidResponse("submit_cancel")
        if idempotency_key in self._cancel_results:
            return self._cancel_results[idempotency_key]
        order = self._orders.get(order_id)
        if order is None or order["order_status"] not in SUBMITTABLE:
            raise OrderNotFound(order_id)
        self._cancel_results[idempotency_key] = "ACCEPTED"
        if kind == "lost_response":
            raise TimeoutError("lost_response")
        return "ACCEPTED"

    def get_cancel_result(self, idempotency_key: str) -> str:
        self._inject("get_cancel_result")
        result = self._cancel_results.get(idempotency_key)
        if result is None:
            raise OrderNotFound(idempotency_key)
        return result
