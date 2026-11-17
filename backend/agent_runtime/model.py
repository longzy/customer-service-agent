"""模型客户端：OpenAI 兼容接口、无密钥时的假模型与配置工厂。"""

import json
from typing import Any, Protocol

import httpx

from backend.agent_runtime.types import Intent


def build_intent_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "emit_intent",
            "description": "输出用户消息的意图与订单号",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["intent"],
                "properties": {
                    "intent": {"type": "string", "enum": [item.value for item in Intent]},
                    "order_id": {"type": ["string", "null"]},
                },
            },
        },
    }


class ModelError(Exception):
    """模型调用失败或输出不可解析。"""


class ModelConfigError(Exception):
    """生产环境缺少模型配置。"""


class ModelClient(Protocol):
    async def classify(self, message: str) -> dict[str, Any]: ...


class FakeModelClient:
    """测试与开发环境使用：按消息精确匹配，未命中返回 UNKNOWN。"""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self._responses = responses or {}

    async def classify(self, message: str) -> dict[str, Any]:
        return self._responses.get(message, {"intent": "UNKNOWN"})


class OpenAICompatibleClient:
    """最小 OpenAI 兼容实现：优先工具调用，缺失时回落到内容中的 JSON。"""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._http = http

    async def classify(self, message: str) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "识别用户消息的意图，只输出工具调用。"},
                {"role": "user", "content": message},
            ],
            "tools": [build_intent_tool()],
            "tool_choice": {"type": "function", "function": {"name": "emit_intent"}},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            http = self._http or httpx.AsyncClient(timeout=10)
            try:
                response = await http.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
            finally:
                if self._http is None:
                    await http.aclose()
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ModelError(str(error)) from error

        try:
            body = response.json()
        except ValueError as error:
            raise ModelError("响应不是合法 JSON") from error
        return self._extract(body)

    def _extract(self, body: Any) -> dict[str, Any]:
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelError("响应缺少 choices") from error

        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            function = tool_calls[0].get("function", {})
            if function.get("name") != "emit_intent":
                raise ModelError("工具名不是 emit_intent")
            arguments = function.get("arguments")
        else:
            arguments = message.get("content")

        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except (TypeError, ValueError) as error:
                raise ModelError("工具参数不是合法 JSON") from error
        else:
            parsed = arguments
        if not isinstance(parsed, dict):
            raise ModelError("模型输出必须是对象")
        return parsed


def build_model_client(settings: Any) -> ModelClient:
    """有密钥时用真实供应商；开发/测试无密钥回落假模型；生产缺配置直接失败。"""
    if getattr(settings, "model_api_key", ""):
        return OpenAICompatibleClient(
            base_url=settings.model_base_url,
            model=settings.model_name,
            api_key=settings.model_api_key,
        )
    if settings.environment in {"development", "test"}:
        return FakeModelClient()
    raise ModelConfigError("生产环境缺少 MODEL_API_KEY")
