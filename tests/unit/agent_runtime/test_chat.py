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


async def test_查询结果使用用户文案_AC_01() -> None:

    chat, _ = service(
        FakeModelClient({"查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}})
    )
    reply = await chat.handle(IDENTITY, "查 ORD-10001")
    assert "待发货" in reply.reply
    assert "PAID_UNFULFILLED" not in reply.reply


async def test_最近订单故障返回通用文案_AC_01() -> None:
    from services.mock_oms.faults import FaultRule

    oms = MockOms()
    oms.faults.add(FaultRule(kind="unavailable", tool="list_recent_orders"))
    chat = ConversationService(
        MemoryRepository(),
        FakeModelClient({"我的订单": {"intent": "QUERY_RECENT"}}),
        build_query_gateway(oms),
    )
    reply = await chat.handle(IDENTITY, "我的订单")
    assert reply.orders == []
    assert "服务暂时不可用" in reply.reply


async def test_内部错误不宣称已转人工_AC_01() -> None:
    class InternalErrorGateway:
        def invoke(self, name, payload, identity, trace_id):
            from services.api.domain.errors import ErrorCode
            from services.tools.gateway import GatewayError, error_envelope

            raise GatewayError(500, error_envelope(ErrorCode.INTERNAL_ERROR))

    chat = ConversationService(
        MemoryRepository(),
        FakeModelClient({"查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}}),
        InternalErrorGateway(),  # type: ignore[arg-type]
    )
    reply = await chat.handle(IDENTITY, "查 ORD-10001")
    assert "已转人工" not in reply.reply
    assert "系统异常" not in reply.reply


async def test_取消与人工意图不冒充已执行_AC_01() -> None:
    chat, _ = service(
        FakeModelClient(
            {
                "取消 ORD-10001": {"intent": "CANCEL_ORDER", "order_id": "ORD-10001"},
                "转人工": {"intent": "HUMAN_HANDOFF"},
            }
        )
    )
    cancel = await chat.handle(IDENTITY, "取消 ORD-10001")
    assert "暂不可用" in cancel.reply
    handoff = await chat.handle(IDENTITY, "转人工")
    assert "后续版本" in handoff.reply


async def test_取消意图返回卡片数据_AC_04() -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    class FakeWorkflow:
        async def request(self, identity, order_id, trace_id):
            return SimpleNamespace(
                id="task-1",
                state=__import__(
                    "services.api.domain.cancellation", fromlist=["CancellationState"]
                ).CancellationState.AWAITING_CONFIRMATION,
                reason_code=None,
                expires_at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
            )

    chat = ConversationService(
        MemoryRepository(),
        FakeModelClient({"取消 ORD-10001": {"intent": "CANCEL_ORDER", "order_id": "ORD-10001"}}),
        build_query_gateway(MockOms()),
        cancellation=FakeWorkflow(),
    )
    reply = await chat.handle(IDENTITY, "取消 ORD-10001")
    assert reply.cancellation is not None
    assert reply.cancellation["task_id"] == "task-1"
    assert reply.cancellation["state_text"] == "等待您确认"
    assert reply.cancellation["order"]["order_id"] == "ORD-10001"
    assert reply.cancellation["order"]["status_text"] == "待发货"


async def test_取消路径网关错误返回文案_AC_04() -> None:
    from services.api.domain.errors import ErrorCode
    from services.tools.gateway import GatewayError, error_envelope

    class FailingWorkflow:
        async def request(self, identity, order_id, trace_id):
            raise GatewayError(503, error_envelope(ErrorCode.DEPENDENCY_UNAVAILABLE))

    chat = ConversationService(
        MemoryRepository(),
        FakeModelClient({"取消 ORD-10001": {"intent": "CANCEL_ORDER", "order_id": "ORD-10001"}}),
        build_query_gateway(MockOms()),
        cancellation=FailingWorkflow(),
    )
    reply = await chat.handle(IDENTITY, "取消 ORD-10001")
    assert reply.cancellation is None
    assert "服务暂时不可用" in reply.reply
