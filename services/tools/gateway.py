"""授权 Tool Gateway：白名单、Schema 校验、归属闸门、错误归一与审计。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from services.api.auth import Identity
from services.api.domain.errors import ErrorCode, error_spec


class DownstreamInvalidResponse(Exception):
    """下游返回非法响应，由网关归类为 INVALID_RESPONSE。"""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    request_model: type[BaseModel]
    handler: Callable[[BaseModel, Identity], Any]
    requires_order: bool = True


class OwnershipIndex:
    """订单归属的本地索引：只回答可见性，不返回订单内容。"""

    def __init__(self) -> None:
        self._owners: dict[str, tuple[str, str]] = {}

    def register(self, order_id: str, tenant_id: str, user_id: str) -> None:
        self._owners[order_id] = (tenant_id, user_id)

    def is_visible(self, order_id: str, tenant_id: str, user_id: str) -> bool:
        return self._owners.get(order_id) == (tenant_id, user_id)


class GatewayError(Exception):
    """网关拒绝：携带 HTTP 状态码与统一错误封套。"""

    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        super().__init__(payload.get("message", "gateway rejected"))
        self.status_code = status_code
        self.payload = payload


def error_envelope(code: ErrorCode) -> dict[str, Any]:
    spec = error_spec(code)
    return {
        "code": code.value,
        "retryable": spec.retryable,
        "visible": spec.visible,
        "message": spec.user_message,
    }


class ToolGateway:
    """所有 Tool 调用的唯一入口。"""

    def __init__(
        self,
        tools: list[ToolSpec],
        ownership: OwnershipIndex,
        audit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._ownership = ownership
        self._audit = audit or (lambda event: None)

    def invoke(self, name: str, payload: dict[str, Any], identity: Identity) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            self._record(tool=name, identity=identity, order_id=None, result="rejected")
            raise GatewayError(404, {"message": "未知工具"})

        try:
            request = tool.request_model.model_validate(payload)
        except ValidationError as error:
            self._record(tool=name, identity=identity, order_id=None, result="rejected")
            raise GatewayError(
                422, {"message": "参数非法", "errors": error.error_count()}
            ) from error

        order_id = getattr(request, "order_id", None)
        if tool.requires_order and not self._ownership.is_visible(
            str(order_id), identity.tenant_id, identity.user_id
        ):
            self._record(tool=name, identity=identity, order_id=order_id, result="rejected")
            raise GatewayError(404, error_envelope(ErrorCode.NOT_FOUND_OR_UNAUTHORIZED))

        try:
            result = tool.handler(request, identity)
        except TimeoutError as error:
            self._record(tool=name, identity=identity, order_id=order_id, result="failed")
            raise GatewayError(504, error_envelope(ErrorCode.DEPENDENCY_TIMEOUT)) from error
        except DownstreamInvalidResponse as error:
            self._record(tool=name, identity=identity, order_id=order_id, result="failed")
            raise GatewayError(502, error_envelope(ErrorCode.INVALID_RESPONSE)) from error
        except Exception as error:  # noqa: BLE001 - 网关必须兜住未知异常，避免泄漏给调用方
            self._record(tool=name, identity=identity, order_id=order_id, result="failed")
            raise GatewayError(500, error_envelope(ErrorCode.INTERNAL_ERROR)) from error

        self._record(tool=name, identity=identity, order_id=order_id, result="ok")
        return result

    def _record(
        self,
        tool: str,
        identity: Identity,
        order_id: Any,
        result: str,
    ) -> None:
        self._audit(
            {
                "tool": tool,
                "tenant_id": identity.tenant_id,
                "user_id": identity.user_id,
                "order_id": order_id,
                "result": result,
            }
        )
