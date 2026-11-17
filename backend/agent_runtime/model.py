"""模型客户端：OpenAI 兼容接口、无密钥时的假模型与配置工厂。"""

import asyncio
import json
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ChatReply:
    """客户聊天模型的一次输出；不含 prompt/response 正文入库。"""

    intent: str
    confidence: float
    reply: str


class ModelClient(Protocol):
    async def classify(self, message: str) -> dict[str, Any]: ...


class ChatModel(Protocol):
    async def respond(self, message: str) -> ChatReply: ...


DEFAULT_FAKE_REPLY = "您好，我是 AI 客服，请描述您的问题。"


FAKE_MODEL_MODES = {"none", "error", "timeout"}


class FakeModelClient:
    """测试与开发环境使用：按消息精确匹配，未命中返回 UNKNOWN。

    mode 仅用于开发/人工演示：error 立即失败，timeout 挂起直到服务端 10s 超时。
    """

    def __init__(
        self,
        responses: dict[str, dict[str, Any]] | None = None,
        mode: str = "none",
    ) -> None:
        self._responses = responses or {}
        self._mode = mode

    async def classify(self, message: str) -> dict[str, Any]:
        return self._responses.get(message, {"intent": "UNKNOWN"})

    async def respond(self, message: str) -> ChatReply:
        if self._mode == "error":
            raise ModelError("假模型故障注入：error")
        if self._mode == "timeout":
            await asyncio.sleep(3600)
            raise ModelError("假模型故障注入：timeout")
        raw = self._responses.get(message, {})
        return ChatReply(
            intent=str(raw.get("intent", "UNKNOWN")),
            confidence=float(raw.get("confidence", 0.9)),
            reply=str(raw.get("reply", DEFAULT_FAKE_REPLY)),
        )


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

    async def _post(self, payload: dict[str, Any]) -> Any:
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
            return response.json()
        except ValueError as error:
            raise ModelError("响应不是合法 JSON") from error

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
        return self._extract(await self._post(payload))

    async def respond(self, message: str) -> ChatReply:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是电商客服 AI。用中文简短回答客户；不确定或需要人工时，"
                        "intent 填 HUMAN_HANDOFF。只输出 JSON："
                        '{"intent":"...","confidence":0.0,"reply":"..."}'
                    ),
                },
                {"role": "user", "content": message},
            ],
            "response_format": {"type": "json_object"},
        }
        body = await self._post(payload)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ModelError("响应缺少 choices") from error
        if not isinstance(content, str):
            raise ModelError("响应内容不是字符串")
        try:
            parsed = json.loads(content)
        except ValueError as error:
            raise ModelError("模型输出不是合法 JSON") from error
        if not isinstance(parsed, dict):
            raise ModelError("模型输出必须是对象")
        intent = parsed.get("intent")
        confidence = parsed.get("confidence")
        reply = parsed.get("reply")
        if not isinstance(intent, str) or not intent.strip():
            raise ModelError("模型输出缺少 intent")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise ModelError("模型输出 confidence 非法")
        if not isinstance(reply, str) or not reply.strip():
            raise ModelError("模型输出缺少 reply")
        return ChatReply(
            intent=intent.strip(),
            confidence=float(confidence),
            reply=reply.strip(),
        )

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
        mode = getattr(settings, "fake_model_mode", "none")
        if mode not in FAKE_MODEL_MODES:
            raise ModelConfigError(f"FAKE_MODEL_MODE 非法：{mode}")
        return FakeModelClient(mode=mode)
    raise ModelConfigError("生产环境缺少 MODEL_API_KEY")
