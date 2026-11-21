"""F-04：低置信/问订单/超范围/自然表达转人工（AC-32）。

- 关键词未命中后仍调用模型；模型 intent=HUMAN_HANDOFF、confidence<0.6、
  订单/超范围意图或回复内容都会转人工入队。
- 转人工时不展示模型回复，避免 AI 编造订单信息。
- 交接单复用 F-03 的完整构造：摘要/最近消息/AI 轨迹/原因/待办/脱敏/order_count=0。
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.agent_runtime.model import ChatReply
from backend.api.main import create_app
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceHandoff,
    ServiceMessage,
)
from tests.integration.customer_support import (
    cleanup_customer_db,
    login_customer,
    prepare_customer_db,
    rows_of,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


class FixedModel:
    """返回固定回复并记录调用；用于验证模型输出是否被展示。"""

    def __init__(self, reply: ChatReply) -> None:
        self.reply = reply
        self.calls: list[str] = []

    async def respond(self, message: str) -> ChatReply:
        self.calls.append(message)
        return self.reply


def app_with(reply: ChatReply) -> tuple[Any, FixedModel]:
    model = FixedModel(reply)
    app = create_app()
    app.state.model_client = model
    return app, model


def send(api: TestClient, content: str) -> Any:
    return api.post(
        "/customer/messages",
        json={"content": content},
        headers={"Idempotency-Key": f"test-{uuid.uuid4()}"},
    )


def only_handoff() -> Any:
    handoffs = rows_of(ServiceHandoff)
    assert len(handoffs) == 1
    return handoffs[0]


def test_模型低置信自动转人工并复用完整交接单_AC_32() -> None:
    content = "这个问题我不太确定，电话13800138000"
    app, model = app_with(
        ChatReply(intent="UNKNOWN", confidence=0.42, reply="我也不太确定，稍后再试。")
    )
    with TestClient(app) as api:
        login_customer(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "QUEUED"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "system"]
        assert body["messages"][1]["content"] == "排队中，请稍候"
    assert model.calls == [content]

    handoff = only_handoff()
    assert handoff.status == "QUEUED"
    assert handoff.reason == "LOW_CONFIDENCE"
    assert handoff.pending_step == "等待坐席接入"
    assert handoff.context["trigger"] == "low_confidence"
    assert handoff.context["order_count"] == 0
    assert handoff.context["customer_username"] == "customer_a"
    assert len(handoff.summary) <= 500
    assert "customer_a" in handoff.summary
    assert "置信" in handoff.summary
    assert "138****8000" in handoff.summary
    assert "13800138000" not in handoff.summary
    assert handoff.context["messages"][-1]["content"].endswith("138****8000")
    trace = handoff.context["ai_trace"]
    assert trace[-1]["event_type"] == "model"
    assert trace[-1]["status"] == "ok"
    assert trace[-1]["confidence"] == pytest.approx(0.42)
    assert "reply" not in trace[-1]
    assert [row.author_type for row in rows_of(ServiceMessage)] == ["customer", "system"]
    assert rows_of(ServiceConversation)[0].status == "QUEUED"
    assert len(rows_of(ServiceAiEvent)) == 1


def test_自然表达要求人工自动转人工_AC_32() -> None:
    content = "能不能帮我转接给同事处理"
    app, model = app_with(
        ChatReply(intent="HUMAN_HANDOFF", confidence=0.93, reply="好的，正在为您转接。")
    )
    with TestClient(app) as api:
        login_customer(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "QUEUED"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "system"]
        assert "正在为您转接" not in response.text
    assert model.calls == [content]

    handoff = only_handoff()
    assert handoff.reason == "LOW_CONFIDENCE"
    assert handoff.context["trigger"] == "model_intent"
    assert handoff.context["order_count"] == 0
    assert "customer_a" in handoff.summary
    trace = handoff.context["ai_trace"]
    assert trace[-1]["event_type"] == "model"
    assert trace[-1]["confidence"] == pytest.approx(0.93)
    assert [row.author_type for row in rows_of(ServiceMessage)] == ["customer", "system"]


def test_模型回复编造订单信息仍转人工且不返回_AC_32() -> None:
    """F-26 起正文里的“订单”由查询分支承接；模型回复仍受编造护栏拦截。

    正文用不含列表入口短语的普通消息，确保确实经过模型回复护栏。
    """
    content = "帮我看看那个东西"
    fabricated = "您的订单 ORD-10001 已发货，预计明天送达。"
    app, model = app_with(ChatReply(intent="UNKNOWN", confidence=0.96, reply=fabricated))
    with TestClient(app) as api:
        login_customer(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "QUEUED"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "system"]
        assert "ORD-10001" not in response.text
        assert fabricated not in response.text
    assert model.calls == [content]

    handoff = only_handoff()
    assert handoff.reason == "OUT_OF_SCOPE"
    assert handoff.context["trigger"] == "model_out_of_scope"
    assert handoff.context["order_count"] == 0
    assert "发货" in handoff.summary
    assert all("ORD-10001" not in row.content for row in rows_of(ServiceMessage))


def test_模型判定取消意图自动转人工_AC_32() -> None:
    content = "帮我看看那个东西"
    app, model = app_with(ChatReply(intent="CANCEL_ORDER", confidence=0.97, reply="好的。"))
    with TestClient(app) as api:
        login_customer(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"
        assert [item["author_type"] for item in response.json()["messages"]] == [
            "customer",
            "system",
        ]
    assert model.calls == [content]

    handoff = only_handoff()
    assert handoff.reason == "OUT_OF_SCOPE"
    assert handoff.context["trigger"] == "out_of_scope_intent"
    assert handoff.context["order_count"] == 0
    assert handoff.summary
    assert [row.author_type for row in rows_of(ServiceMessage)] == ["customer", "system"]


def test_模型回复编造订单信息被拦截_AC_32() -> None:
    content = "你好呀"
    fabricated = "您好，您的订单 ORD-20002 已签收。"
    app, model = app_with(ChatReply(intent="UNKNOWN", confidence=0.98, reply=fabricated))
    with TestClient(app) as api:
        login_customer(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "QUEUED"
        assert "ORD-20002" not in response.text
    assert model.calls == [content]

    handoff = only_handoff()
    assert handoff.reason == "OUT_OF_SCOPE"
    assert handoff.context["trigger"] == "model_out_of_scope"
    assert handoff.context["order_count"] == 0
    assert [row.author_type for row in rows_of(ServiceMessage)] == ["customer", "system"]
    assert all("ORD-20002" not in row.content for row in rows_of(ServiceMessage))


def test_高置信普通消息仍返回AI回复_AC_32() -> None:
    content = "你好"
    app, model = app_with(
        ChatReply(intent="UNKNOWN", confidence=0.9, reply="您好，请问有什么可以帮您？")
    )
    with TestClient(app) as api:
        login_customer(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "AI_ACTIVE"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "ai"]
        assert body["messages"][1]["content"] == "您好，请问有什么可以帮您？"
    assert model.calls == [content]
    assert rows_of(ServiceHandoff) == []


@pytest.mark.parametrize(("confidence", "expected_status"), [(0.6, "AI_ACTIVE"), (0.59, "QUEUED")])
def test_低置信阈值0_6边界_AC_32(confidence: float, expected_status: str) -> None:
    content = "在吗"
    app, _ = app_with(ChatReply(intent="UNKNOWN", confidence=confidence, reply="在的。"))
    with TestClient(app) as api:
        login_customer(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected_status

    if expected_status == "AI_ACTIVE":
        assert rows_of(ServiceHandoff) == []
    else:
        assert only_handoff().reason == "LOW_CONFIDENCE"


def test_排队中再问订单不重复建单_AC_32() -> None:
    app, model = app_with(ChatReply(intent="UNKNOWN", confidence=0.9, reply="您的订单已发货。"))
    with TestClient(app) as api:
        login_customer(api)
        first = send(api, "转人工")
        second = send(api, "我的订单")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["status"] == "QUEUED"
        assert second.json()["status"] == "QUEUED"
        assert [item["author_type"] for item in second.json()["messages"]] == ["customer"]
    assert model.calls == []
    assert len(rows_of(ServiceHandoff)) == 1
