"""对话编排：查询、澄清、错误与持久化（AC-01、AC-08）。"""

from typing import Any

import pytest

from services.agent_runtime.chat import ConversationService
from services.agent_runtime.model import FakeModelClient
from services.api.auth import Identity
from services.mock_oms.service import MockOms
from services.tools.query import build_query_gateway

IDENTITY = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")


class MemoryRepository:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str, str]] = []
        self.conversations: dict[str, str] = {}

    async def get_or_create(self, identity: Identity, conversation_id: str | None) -> str:
        conversation = conversation_id or "conv-1"
        self.conversations[conversation] = identity.user_id
        return conversation

    async def add_message(
        self, conversation_id: str, role: str, content: str, trace_id: str
    ) -> None:
        self.messages.append((conversation_id, role, content, trace_id))

    async def commit(self) -> None:
        return None


def service(
    model: FakeModelClient, repository: MemoryRepository | None = None
) -> tuple[ConversationService, MemoryRepository]:
    repo = repository or MemoryRepository()
    return ConversationService(repo, model, build_query_gateway(MockOms())), repo


async def test_查询订单返回摘要并落库_AC_01() -> None:
    chat, repo = service(
        FakeModelClient({"查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}})
    )
    reply = await chat.handle(IDENTITY, "查 ORD-10001")
    assert reply.orders and reply.orders[0]["order_id"] == "ORD-10001"
    assert "ORD-10001" in reply.reply
    assert [(role, trace) for _, role, _, trace in repo.messages] == [
        ("user", reply.trace_id),
        ("assistant", reply.trace_id),
    ]


async def test_多候选返回澄清且不调用工具_AC_08() -> None:
    chat, repo = service(FakeModelClient({"查 ORD-10001 和 ORD-10002": {"intent": "QUERY_ORDER"}}))
    reply = await chat.handle(IDENTITY, "查 ORD-10001 和 ORD-10002")
    assert reply.orders == []
    assert reply.clarification == ["ORD-10001", "ORD-10002"]
    assert "请确认" in reply.reply


async def test_越权查询返回统一文案_AC_01() -> None:
    chat, _ = service(
        FakeModelClient({"查 ORD-10005": {"intent": "QUERY_ORDER", "order_id": "ORD-10005"}})
    )
    reply = await chat.handle(IDENTITY, "查 ORD-10005")
    assert reply.orders == []
    assert "查无此单" in reply.reply or "未找到" in reply.reply


async def test_模型错误向上抛出_AC_01() -> None:
    class Broken:
        async def classify(self, message: str) -> dict[str, Any]:
            raise RuntimeError("down")

    chat = ConversationService(MemoryRepository(), Broken(), build_query_gateway(MockOms()))
    with pytest.raises(RuntimeError):
        await chat.handle(IDENTITY, "查 ORD-10001")
