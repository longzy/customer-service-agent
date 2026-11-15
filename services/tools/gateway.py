"""授权 Tool Gateway：以契约 JSON Schema 为唯一校验来源。

职责：白名单、契约校验、身份字段剥离、订单归属闸门、错误归一与审计。
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from services.api.auth import Identity
from services.api.domain.errors import ErrorCode, error_spec
from services.errors import (
    CancelRejected,
    DownstreamInvalidResponse,
    IdempotencyConflict,
    OrderNotFound,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"
TOOLS_DIR = CONTRACTS / "tools"

IDENTITY_FIELDS = {"tenant_id", "user_id"}


def _load_documents() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    domain = json.loads((CONTRACTS / "schemas" / "domain.json").read_text(encoding="utf-8"))
    tools = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(TOOLS_DIR.glob("*.json"))
        if path.name != "openapi.json"
    }
    return domain, tools


def _registry(domain: dict[str, Any], tools: dict[str, dict[str, Any]]) -> Registry:
    resources = [(domain["$id"], Resource.from_contents(domain))]
    resources.extend((doc["$id"], Resource.from_contents(doc)) for doc in tools.values())
    return Registry().with_resources(resources)


@dataclass(frozen=True)
class ToolSpec:
    """一个 Tool 的执行契约：参数以 contracts 下的 Schema 为准。"""

    name: str
    handler: Callable[[dict[str, Any], Identity, str], Any]
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
    """网关拒绝：携带 HTTP 状态码与响应体。"""

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


def has_identity_fields(payload: dict[str, Any]) -> bool:
    """请求体不得携带身份字段；调用方身份只能来自会话。"""
    return bool(IDENTITY_FIELDS & set(payload))


class ToolGateway:
    """所有 Tool 调用的唯一入口。"""

    def __init__(
        self,
        tools: list[ToolSpec],
        ownership: OwnershipIndex,
        audit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        domain, documents = _load_documents()
        registry = _registry(domain, documents)
        self._tools: dict[str, ToolSpec] = {tool.name: tool for tool in tools}
        self._errors: dict[str, set[str]] = {
            name: set(doc["x-error-codes"]) for name, doc in documents.items()
        }
        self._validators: dict[str, Draft202012Validator] = {
            name: Draft202012Validator({"$ref": f"{doc['$id']}#/$defs/Request"}, registry=registry)
            for name, doc in documents.items()
        }
        missing = set(self._tools) - set(self._validators)
        if missing:
            raise ValueError(f"缺少契约的工具：{sorted(missing)}")
        self._ownership = ownership
        self._audit = audit or (lambda event: None)

    def invoke(
        self,
        name: str,
        payload: dict[str, Any],
        identity: Identity,
        trace_id: str,
    ) -> Any:
        if not trace_id:
            self._record(name, identity, None, "rejected", "INTERNAL_ERROR", None)
            raise GatewayError(500, error_envelope(ErrorCode.INTERNAL_ERROR))
        if not isinstance(payload, dict):
            self._record(name, identity, None, "rejected", "INVALID_ARGUMENT", trace_id)
            raise GatewayError(422, {"message": "参数非法"})

        tool = self._tools.get(name)
        if tool is None:
            self._record(name, identity, None, "rejected", "UNKNOWN_TOOL", trace_id)
            raise GatewayError(404, {"message": "未知工具"})

        if has_identity_fields(payload):
            self._record(name, identity, None, "rejected", "INVALID_ARGUMENT", trace_id)
            raise GatewayError(422, {"message": "参数非法"})

        errors = list(self._validators[name].iter_errors(payload))
        if errors:
            self._record(name, identity, None, "rejected", "INVALID_ARGUMENT", trace_id)
            raise GatewayError(422, {"message": "参数非法", "errors": len(errors)})

        order_id = payload.get("order_id")
        if tool.requires_order:
            if not isinstance(order_id, str) or not order_id:
                self._record(name, identity, None, "rejected", "INVALID_ARGUMENT", trace_id)
                raise GatewayError(422, {"message": "参数非法"})
            if not self._ownership.is_visible(order_id, identity.tenant_id, identity.user_id):
                self._record(
                    name, identity, order_id, "rejected", "NOT_FOUND_OR_UNAUTHORIZED", trace_id
                )
                raise GatewayError(404, error_envelope(ErrorCode.NOT_FOUND_OR_UNAUTHORIZED))

        try:
            result = tool.handler(dict(payload), identity, trace_id)
        except TimeoutError as error:
            code = self._timeout_code(name)
            self._record(name, identity, order_id, "failed", code.value, trace_id)
            raise GatewayError(504, error_envelope(code)) from error
        except DownstreamInvalidResponse as error:
            self._record(name, identity, order_id, "failed", "INVALID_RESPONSE", trace_id)
            raise GatewayError(502, error_envelope(ErrorCode.INVALID_RESPONSE)) from error
        except (CancelRejected, IdempotencyConflict) as error:
            self._record(name, identity, order_id, "failed", "OMS_REJECTED", trace_id)
            raise GatewayError(409, error_envelope(ErrorCode.OMS_REJECTED)) from error
        except OrderNotFound as error:
            self._record(name, identity, order_id, "failed", "NOT_FOUND_OR_UNAUTHORIZED", trace_id)
            raise GatewayError(404, error_envelope(ErrorCode.NOT_FOUND_OR_UNAUTHORIZED)) from error
        except ConnectionError as error:
            code = (
                ErrorCode.DEPENDENCY_UNAVAILABLE
                if ErrorCode.DEPENDENCY_UNAVAILABLE.value in self._errors[name]
                else ErrorCode.INTERNAL_ERROR
            )
            self._record(name, identity, order_id, "failed", code.value, trace_id)
            raise GatewayError(503, error_envelope(code)) from error
        except Exception as error:  # noqa: BLE001 - 网关必须兜住未知异常
            self._record(name, identity, order_id, "failed", "INTERNAL_ERROR", trace_id)
            raise GatewayError(500, error_envelope(ErrorCode.INTERNAL_ERROR)) from error

        self._record(name, identity, order_id, "ok", None, trace_id)
        return result

    def _timeout_code(self, name: str) -> ErrorCode:
        if ErrorCode.DEPENDENCY_TIMEOUT.value in self._errors[name]:
            return ErrorCode.DEPENDENCY_TIMEOUT
        return ErrorCode.DEPENDENCY_UNAVAILABLE

    def _record(
        self,
        tool: str,
        identity: Identity,
        order_id: Any,
        result: str,
        error_code: str | None,
        trace_id: str | None,
    ) -> None:
        event = {
            "tool": tool,
            "tenant_id": identity.tenant_id,
            "user_id": identity.user_id,
            "order_id": order_id,
            "result": result,
            "error_code": error_code,
            "trace_id": trace_id,
        }
        try:
            self._audit(event)
        except Exception as error:  # noqa: BLE001 - 审计失败按失败关闭处理
            raise GatewayError(500, error_envelope(ErrorCode.INTERNAL_ERROR)) from error
