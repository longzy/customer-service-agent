"""模型客户端：假模型与 OpenAI 兼容解析（AC-01）。"""

import json

import httpx
import pytest

from services.agent_runtime.model import FakeModelClient, ModelError, OpenAICompatibleClient


async def test_假模型按消息返回() -> None:
    client = FakeModelClient({"查 ORD-1": {"intent": "QUERY_ORDER", "order_id": "ORD-1"}})
    assert await client.classify("查 ORD-1") == {"intent": "QUERY_ORDER", "order_id": "ORD-1"}


async def test_假模型未命中返回未知() -> None:
    assert await FakeModelClient({}).classify("随便") == {"intent": "UNKNOWN"}


async def test_兼容接口解析工具调用() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "emit_intent",
                                        "arguments": json.dumps(
                                            {"intent": "QUERY_ORDER", "order_id": "ORD-1"}
                                        ),
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenAICompatibleClient(
            base_url="https://example.test/v1", model="m", api_key="k", http=http
        )
        result = await client.classify("查 ORD-1")
    assert result == {"intent": "QUERY_ORDER", "order_id": "ORD-1"}


async def test_兼容接口缺少工具调用时报错() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
    )
    async with httpx.AsyncClient(transport=transport) as http:
        client = OpenAICompatibleClient(
            base_url="https://example.test/v1", model="m", api_key="k", http=http
        )
        with pytest.raises(ModelError):
            await client.classify("查 ORD-1")
