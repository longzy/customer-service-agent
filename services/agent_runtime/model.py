"""模型客户端：OpenAI 兼容接口与默认假模型。

真实供应商通过环境变量配置；没有密钥时使用假模型，测试不联网。
"""

import json
from typing import Any, Protocol

import httpx

EMIT_INTENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "emit_intent",
        "description": "输出用户消息的意图与订单号",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["intent"],
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "QUERY_ORDER",
                        "QUERY_RECENT",
                        "CANCEL_ORDER",
                        "CONFIRM_CANCEL",
                        "HUMAN_HANDOFF",
                        "UNKNOWN",
                    ],
                },
                "order_id": {"type": ["string", "null"]},
            },
        },
    },
}


class ModelError(Exception):
    """模型调用失败或输出不可解析。"""


class ModelClient(Protocol):
    async def classify(self, message: str) -> dict[str, Any]: ...


class FakeModelClient:
    """测试与无密钥环境使用：按消息精确匹配，未命中返回 UNKNOWN。"""

    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self._responses = responses

    async def classify(self, message: str) -> dict[str, Any]:
        return self._responses.get(message, {"intent": "UNKNOWN"})


class OpenAICompatibleClient:
    """最小 OpenAI 兼容实现：只调用 chat/completions 的工具模式。"""

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
            "tools": [EMIT_INTENT_TOOL],
            "tool_choice": {"type": "function", "function": {"name": "emit_intent"}},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            if self._http is not None:
                response = await self._http.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
            else:
                async with httpx.AsyncClient(timeout=10) as http:
                    response = await http.post(
                        f"{self._base_url}/chat/completions", json=payload, headers=headers
                    )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ModelError(str(error)) from error

        body = response.json()
        try:
            tool_call = body["choices"][0]["message"]["tool_calls"][0]
            arguments = tool_call["function"]["arguments"]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelError("模型未返回工具调用") from error
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise ModelError("工具参数不是合法 JSON") from error
        if not isinstance(parsed, dict):
            raise ModelError("工具参数必须是对象")
        return parsed
