"""HTTP OMS Adapter：把约定的 HTTP 契约映射到 OmsPort。"""

from __future__ import annotations

from typing import Any, cast

import httpx

from services.adapters.oms.port import CANCEL_RESULT_STATES, OmsAccess
from services.domain.orders import OrderDetail
from services.errors import (
    DownstreamInvalidResponse,
    IdempotencyConflict,
    OrderNotFound,
)


class HttpOmsAdapter:
    """同步 HTTP 客户端；业务层只看到 OmsPort。"""

    def __init__(
        self,
        base_url: str,
        timeout: float = 2.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = (
            client if client is not None else httpx.Client(base_url=base_url, timeout=timeout)
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self, access: OmsAccess) -> dict[str, str]:
        headers = {"X-Tenant-Id": access.tenant_id}
        if access.user_id is not None:
            headers["X-User-Id"] = access.user_id
        return headers

    def _json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as error:
            raise DownstreamInvalidResponse("OMS 返回非 JSON") from error

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 404:
            raise OrderNotFound(response.request.url.path)
        if response.status_code == 409:
            raise IdempotencyConflict(response.request.url.path)
        if response.status_code >= 400:
            raise ConnectionError(f"OMS HTTP {response.status_code}")

    def _send(
        self,
        method: str,
        path: str,
        access: OmsAccess,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = self._client.request(method, path, headers=self._headers(access), **kwargs)
        except httpx.TimeoutException as error:
            raise TimeoutError(path) from error
        except httpx.ConnectError as error:
            raise ConnectionError(path) from error
        self._raise_for_status(response)
        return response

    def _order(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise DownstreamInvalidResponse("OMS 订单不是对象")
        try:
            OrderDetail.model_validate(payload)
        except ValueError as error:
            raise DownstreamInvalidResponse("OMS 订单字段非法") from error
        return cast(dict[str, Any], payload)

    def _state(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            raise DownstreamInvalidResponse("OMS 结果不是对象")
        state = payload.get("state")
        if state not in CANCEL_RESULT_STATES:
            raise DownstreamInvalidResponse("OMS 取消状态非法")
        return cast(str, state)

    def is_visible(self, access: OmsAccess, order_id: str) -> bool:
        try:
            response = self._client.get(
                f"/orders/{order_id}/visibility", headers=self._headers(access)
            )
        except httpx.TimeoutException as error:
            raise TimeoutError(order_id) from error
        except httpx.ConnectError as error:
            raise ConnectionError(order_id) from error
        if response.status_code == 404:
            return False
        self._raise_for_status(response)
        payload = self._json(response)
        visible = payload.get("visible") if isinstance(payload, dict) else None
        if not isinstance(visible, bool):
            raise DownstreamInvalidResponse("OMS 可见性结果非法")
        return visible

    def get_order(self, access: OmsAccess, order_id: str) -> dict[str, Any]:
        response = self._send("GET", f"/orders/{order_id}", access)
        return self._order(self._json(response))

    def list_recent_orders(self, access: OmsAccess, limit: int = 5) -> list[dict[str, Any]]:
        if limit < 0:
            raise ValueError("limit 不能为负")
        response = self._send("GET", "/orders", access, params={"limit": limit})
        payload = self._json(response)
        if not isinstance(payload, list):
            raise DownstreamInvalidResponse("OMS 订单列表不是数组")
        return [self._order(item) for item in payload]

    def submit_cancel(self, access: OmsAccess, order_id: str, idempotency_key: str) -> str:
        response = self._send(
            "POST",
            f"/orders/{order_id}/cancellations",
            access,
            json={"idempotency_key": idempotency_key},
        )
        return self._state(self._json(response))

    def get_cancel_result(self, tenant_id: str, idempotency_key: str) -> str:
        access = OmsAccess(tenant_id=tenant_id)
        response = self._send("GET", f"/cancellations/{idempotency_key}", access)
        return self._state(self._json(response))
