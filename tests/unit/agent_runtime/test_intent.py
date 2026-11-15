"""意图识别与澄清判定（基座 + AC-08）。"""

import pytest

from services.agent_runtime.intent import IntentError, classify_message
from services.agent_runtime.model import FakeModelClient
from services.agent_runtime.types import Intent


def fake(intent: str, order_id: str | None = None) -> FakeModelClient:
    return FakeModelClient({})


async def test_查询单个订单_基座豁免() -> None:
    client = FakeModelClient(
        {"查一下 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}}
    )
    result = await classify_message("查一下 ORD-10001", client)
    assert result.intent == Intent.QUERY_ORDER
    assert result.order_id == "ORD-10001"


async def test_查询最近订单_基座豁免() -> None:
    client = FakeModelClient({"我的订单到哪了": {"intent": "QUERY_RECENT"}})
    result = await classify_message("我的订单到哪了", client)
    assert result.intent == Intent.QUERY_RECENT


async def test_人工转接意图_基座豁免() -> None:
    client = FakeModelClient({"转人工": {"intent": "HUMAN_HANDOFF"}})
    result = await classify_message("转人工", client)
    assert result.intent == Intent.HUMAN_HANDOFF


async def test_取消意图缺订单号要求澄清_AC_08() -> None:
    client = FakeModelClient({"取消订单": {"intent": "CANCEL_ORDER"}})
    result = await classify_message("取消订单", client)
    assert result.intent == Intent.CANCEL_ORDER
    assert result.needs_clarification is True


async def test_多候选订单要求澄清且不选目标_AC_08() -> None:
    client = FakeModelClient(
        {"查 ORD-10001 和 ORD-10002": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}}
    )
    result = await classify_message("查 ORD-10001 和 ORD-10002", client)
    assert result.needs_clarification is True
    assert result.order_id is None
    assert result.candidate_order_ids == ["ORD-10001", "ORD-10002"]


async def test_模型返回未提及订单号被拒绝_AC_08() -> None:
    client = FakeModelClient({"查一下": {"intent": "QUERY_ORDER", "order_id": "ORD-20001"}})
    with pytest.raises(IntentError):
        await classify_message("查一下", client)


async def test_模型订单号与消息不一致时以消息为准_AC_08() -> None:
    client = FakeModelClient({"查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-20001"}})
    result = await classify_message("查 ORD-10001", client)
    assert result.order_id == "ORD-10001"


async def test_订单号大小写与小写格式_基座豁免() -> None:
    client = FakeModelClient({"查 ord-10001": {"intent": "QUERY_ORDER"}})
    result = await classify_message("查 ord-10001", client)
    assert result.order_id == "ORD-10001"


async def test_相似前缀不误判_基座豁免() -> None:
    result = await classify_message("查 XORD-10001", FakeModelClient({}))
    assert result.candidate_order_ids == []


async def test_非法模型输出被拒绝_基座豁免() -> None:
    client = FakeModelClient({"查单": {"intent": "NOT_AN_INTENT"}})
    with pytest.raises(IntentError):
        await classify_message("查单", client)


async def test_未识别消息为未知意图_基座豁免() -> None:
    result = await classify_message("今天天气不错", FakeModelClient({}))
    assert result.intent == Intent.UNKNOWN
