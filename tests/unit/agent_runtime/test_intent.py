"""意图识别与澄清判定（AC-01、AC-08）。"""

import pytest

from services.agent_runtime.intent import Intent, IntentError, classify_message
from services.agent_runtime.model import FakeModelClient, ModelError


async def test_查询单个订单_AC_01() -> None:
    client = FakeModelClient(
        {"查一下 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}}
    )
    result = await classify_message("查一下 ORD-10001", client)
    assert result.intent == Intent.QUERY_ORDER
    assert result.order_id == "ORD-10001"
    assert result.needs_clarification is False


async def test_查询最近订单_AC_01() -> None:
    client = FakeModelClient({"我的订单到哪了": {"intent": "QUERY_RECENT"}})
    result = await classify_message("我的订单到哪了", client)
    assert result.intent == Intent.QUERY_RECENT


async def test_取消意图缺订单号要求澄清_AC_08() -> None:
    client = FakeModelClient({"取消订单": {"intent": "CANCEL_ORDER"}})
    result = await classify_message("取消订单", client)
    assert result.intent == Intent.CANCEL_ORDER
    assert result.needs_clarification is True


async def test_多候选订单要求澄清_AC_08() -> None:
    client = FakeModelClient({})
    result = await classify_message("查 ORD-10001 和 ORD-10002", client)
    assert result.needs_clarification is True
    assert result.candidate_order_ids == ["ORD-10001", "ORD-10002"]


async def test_非法模型输出被拒绝_AC_01() -> None:
    client = FakeModelClient({"查单": {"intent": "NOT_AN_INTENT"}})
    with pytest.raises(IntentError):
        await classify_message("查单", client)


async def test_未识别消息为未知意图_AC_01() -> None:
    result = await classify_message("今天天气不错", FakeModelClient({}))
    assert result.intent == Intent.UNKNOWN


async def test_模型错误向上抛出_AC_01() -> None:
    class Broken:
        async def classify(self, message: str) -> dict:
            raise ModelError("boom")

    with pytest.raises(ModelError):
        await classify_message("查单", Broken())
