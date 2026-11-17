"""模型客户端：工厂、请求形状、解析与失败路径。"""

import json
from typing import Any

import httpx
import pytest

from backend.agent_runtime.model import (
    FakeModelClient,
    ModelConfigError,
    ModelError,
    OpenAICompatibleClient,
    build_intent_tool,
    build_model_client,
)
from backend.agent_runtime.types import Intent


def transport(handler: Any) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def classify_with(handler: Any, message: str = "查 ORD-1") -> dict[str, Any]:
    async with httpx.AsyncClient(transport=transport(handler)) as http:
        client = OpenAICompatibleClient(
            base_url="https://example.test/v1", model="m", api_key="k", http=http
        )
        return await client.classify(message)


def success_body(arguments: dict[str, Any], name: str = "emit_intent") -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [{"function": {"name": name, "arguments": json.dumps(arguments)}}]
                }
            }
        ]
    }


def test_工具枚举与意图一致_基座豁免() -> None:
    schema = build_intent_tool()
    enum = schema["function"]["parameters"]["properties"]["intent"]["enum"]
    assert enum == [item.value for item in Intent]


async def test_假模型按消息返回_基座豁免() -> None:
    client = FakeModelClient({"查 ORD-1": {"intent": "QUERY_ORDER", "order_id": "ORD-1"}})
    assert await client.classify("查 ORD-1") == {"intent": "QUERY_ORDER", "order_id": "ORD-1"}


async def test_假模型未命中返回未知_基座豁免() -> None:
    assert await FakeModelClient().classify("随便") == {"intent": "UNKNOWN"}


async def test_请求形状正确_基座豁免() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=success_body({"intent": "QUERY_ORDER"}))

    await classify_with(handler)
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "m"
    assert seen["body"]["tools"][0]["function"]["name"] == "emit_intent"
    assert seen["body"]["tool_choice"]["function"]["name"] == "emit_intent"


async def test_兼容接口解析工具调用_基座豁免() -> None:
    result = await classify_with(
        lambda request: httpx.Response(
            200, json=success_body({"intent": "QUERY_ORDER", "order_id": "ORD-1"})
        )
    )
    assert result == {"intent": "QUERY_ORDER", "order_id": "ORD-1"}


async def test_无工具调用时回落内容JSON_基座豁免() -> None:
    result = await classify_with(
        lambda request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"intent": "QUERY_RECENT"})}}]},
        )
    )
    assert result == {"intent": "QUERY_RECENT"}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]}),
        httpx.Response(200, json=success_body({"intent": "x"}, name="other_tool")),
    ],
)
async def test_异常响应统一为模型错误_基座豁免(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if response.status_code == 200 and response.content == b"not json":
            return httpx.Response(200, text="not json")
        return response

    with pytest.raises(ModelError):
        await classify_with(handler)


async def test_网络超时映射为模型错误_基座豁免() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModelError):
        await classify_with(handler)


def test_开发环境无密钥使用假模型_基座豁免() -> None:
    class Dev:
        environment = "development"
        model_api_key = ""
        model_base_url = "x"
        model_name = "m"

    assert isinstance(build_model_client(Dev()), FakeModelClient)


def test_生产环境无密钥直接失败_基座豁免() -> None:
    class Prod:
        environment = "production"
        model_api_key = ""
        model_base_url = "x"
        model_name = "m"

    with pytest.raises(ModelConfigError):
        build_model_client(Prod())


def test_有密钥使用真实客户端_基座豁免() -> None:
    class Dev:
        environment = "development"
        model_api_key = "k"
        model_base_url = "https://example.test/v1"
        model_name = "m"

    assert isinstance(build_model_client(Dev()), OpenAICompatibleClient)


async def respond_with(handler: Any, message: str = "你好") -> Any:
    async with httpx.AsyncClient(transport=transport(handler)) as http:
        client = OpenAICompatibleClient(
            base_url="https://example.test/v1", model="m", api_key="k", http=http
        )
        return await client.respond(message)


def chat_body(payload: dict[str, Any]) -> dict[str, Any]:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


async def test_假模型应答包含意图置信度与回复_基座豁免() -> None:
    client = FakeModelClient(
        {"你好": {"intent": "UNKNOWN", "confidence": 0.8, "reply": "您好，请讲。"}}
    )
    reply = await client.respond("你好")
    assert (reply.intent, reply.confidence, reply.reply) == ("UNKNOWN", 0.8, "您好，请讲。")


async def test_假模型未命中使用默认回复_基座豁免() -> None:
    reply = await FakeModelClient().respond("随便")
    assert reply.intent == "UNKNOWN"
    assert reply.confidence == 0.9
    assert reply.reply


async def test_兼容接口解析聊天回复_基座豁免() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=chat_body({"intent": "HUMAN_HANDOFF", "confidence": 0.4, "reply": "稍等。"}),
        )

    reply = await respond_with(handler)
    assert (reply.intent, reply.confidence, reply.reply) == ("HUMAN_HANDOFF", 0.4, "稍等。")
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "tools" not in seen["body"]


@pytest.mark.parametrize(
    "payload",
    [
        {"intent": "", "confidence": 0.5, "reply": "x"},
        {"intent": "UNKNOWN", "confidence": 1.5, "reply": "x"},
        {"intent": "UNKNOWN", "confidence": "high", "reply": "x"},
        {"intent": "UNKNOWN", "confidence": 0.5, "reply": ""},
    ],
)
async def test_聊天回复非法字段统一为模型错误_基座豁免(payload: dict[str, Any]) -> None:
    with pytest.raises(ModelError):
        await respond_with(lambda request: httpx.Response(200, json=chat_body(payload)))


async def test_假模型故障注入立即失败_基座豁免() -> None:
    with pytest.raises(ModelError):
        await FakeModelClient(mode="error").respond("你好")


def test_非法假模型模式启动失败_基座豁免() -> None:
    class Dev:
        environment = "development"
        model_api_key = ""
        model_base_url = "x"
        model_name = "m"
        fake_model_mode = "bogus"

    with pytest.raises(ModelConfigError):
        build_model_client(Dev())
