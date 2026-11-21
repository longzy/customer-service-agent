"""F-03：关键词转人工与完整交接单（AC-32）。

- 4 个关键词及空白/标点变体命中后不调用模型，直接入队并写完整交接单。
- 交接单：摘要 ≤500、最近 20 条且正文 ≤4000 字、AI 轨迹、原因、待办、脱敏、order_count=0。
- 模型失败路径复用同一构造，避免出现两套交接单上下文。
"""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.agent_runtime.model import DEFAULT_FAKE_REPLY, ChatReply, FakeModelClient, ModelError
from backend.api.main import create_app
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceHandoff,
    ServiceMessage,
)
from tests.integration.customer_support import (
    DEMO_CREDENTIAL,
    cleanup_customer_db,
    prepare_customer_db,
)
from tests.integration.customer_support import (
    rows_of as rows,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


class CountingModel:
    """记录模型调用次数；关键词命中时调用次数必须为 0。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def respond(self, message: str) -> ChatReply:
        self.calls.append(message)
        return ChatReply(intent="UNKNOWN", confidence=0.95, reply="您好，我是 AI 客服。")


class ErrorModel:
    async def respond(self, _message: str) -> Any:
        raise ModelError("down")


def api_client(app: Any = None) -> TestClient:
    return TestClient(app or create_app())


def login(api: TestClient, username: str = "customer_a") -> Any:
    response = api.post(
        "/customer/sessions",
        json={"username": username, "password": DEMO_CREDENTIAL},
    )
    assert response.status_code == 200, response.text
    return response


def send(api: TestClient, content: str, key: str | None = None) -> Any:
    return api.post(
        "/customer/messages",
        json={"content": content},
        headers={"Idempotency-Key": key or f"test-{uuid.uuid4()}"},
    )


def only_handoff() -> Any:
    handoffs = rows(ServiceHandoff)
    assert len(handoffs) == 1
    return handoffs[0]


@pytest.mark.parametrize(
    "content",
    [
        "转人工",
        "人工客服",
        "真人",
        "找人工",
        "我要转 人工！",
        "转，人工",
        "转-人工",
        "转\n人工",
        "转人工，谢谢",
    ],
)
def test_关键词命中直接入队且不调用模型_AC_32(content: str) -> None:
    model = CountingModel()
    app = create_app()
    app.state.model_client = model
    with api_client(app) as api:
        login(api)
        response = send(api, content)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "QUEUED"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "system"]
        assert body["messages"][1]["content"] == "排队中，请稍候"

    assert model.calls == []
    handoff = only_handoff()
    assert handoff.status == "QUEUED"
    assert handoff.reason == "CUSTOMER_REQUEST"
    assert handoff.priority == "normal"
    assert handoff.pending_step
    assert handoff.summary
    assert len(handoff.summary) <= 500
    assert "customer_a" in handoff.summary
    # F-28：关键词转人工时补查一次最近订单，交接单带真实订单上下文（003 AC-55）。
    assert handoff.context["order_count"] == 4
    assert handoff.context["order_context_status"] == "ok"
    assert len(handoff.context["orders"]) == 4
    assert handoff.context["trigger"] == "keyword"
    assert handoff.context["customer_username"] == "customer_a"
    assert handoff.context["customer_display_name"] == "客户甲"
    assert handoff.context["matched_keyword"] in {"转人工", "人工客服", "真人", "找人工"}
    assert handoff.journey_id == rows(ServiceConversation)[0].journey_id

    messages = handoff.context["messages"]
    assert messages
    assert messages[-1]["author_type"] == "customer"
    assert messages[-1]["content"] == content

    trace = handoff.context["ai_trace"]
    # 轨迹是坐席可见投影：只要求保留这次转人工的 intent 事件与事件元数据；
    # 不把后续 feature 新增的查询事件写死（001 契约，003 演进不再回来改）。
    assert any(item["event_type"] == "intent" and item["status"] == "matched" for item in trace)
    assert all("reply" not in item for item in trace)

    events = rows(ServiceAiEvent)
    event_pairs = {(event.event_type, event.status) for event in events}
    assert ("intent", "matched") in event_pairs
    # 关键词转人工不调用模型：不得出现 model 事件（行为契约）。
    assert "model" not in {event.event_type for event in events}
    assert [row.author_type for row in rows(ServiceMessage)] == ["customer", "system"]
    assert rows(ServiceConversation)[0].status == "QUEUED"


def test_普通消息未命中关键词仍调用模型_AC_32() -> None:
    model = CountingModel()
    app = create_app()
    app.state.model_client = model
    with api_client(app) as api:
        login(api)
        response = send(api, "你好")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "AI_ACTIVE"
        assert [item["author_type"] for item in response.json()["messages"]] == ["customer", "ai"]

    assert model.calls == ["你好"]
    assert rows(ServiceHandoff) == []


def test_交接单只保留最近20条消息_AC_32() -> None:
    app = create_app()
    app.state.model_client = FakeModelClient({})
    with api_client(app) as api:
        login(api)
        for index in range(25):
            assert send(api, f"消息{index}").status_code == 200
        assert send(api, "转人工").status_code == 200

    handoff = only_handoff()
    messages = handoff.context["messages"]
    assert len(messages) == 20
    assert messages[-1]["content"] == "转人工"
    assert messages[0]["content"] == DEFAULT_FAKE_REPLY
    assert messages[1]["content"] == "消息16"
    assert all(item["content"] != "消息15" for item in messages)
    assert sum(len(item["content"]) for item in messages) <= 4000

    trace = handoff.context["ai_trace"]
    trace_types = [item["event_type"] for item in trace]
    assert "intent" in trace_types
    assert "model" in trace_types
    assert all("reply" not in item for item in trace)


def test_交接单正文超过4000字时从旧消息截断_AC_32() -> None:
    long_message = "测" * 499
    app = create_app()
    app.state.model_client = FakeModelClient({})
    with api_client(app) as api:
        login(api)
        for index in range(10):
            assert send(api, f"{index}{long_message}").status_code == 200
        assert send(api, "转人工").status_code == 200

    handoff = only_handoff()
    messages = handoff.context["messages"]
    assert len(messages) <= 20
    assert sum(len(item["content"]) for item in messages) == 4000
    assert messages[-1]["content"] == "转人工"
    assert len(messages[0]["content"]) < 501
    assert any(item["content"] == "9" + long_message for item in messages)
    assert any(item["content"] == DEFAULT_FAKE_REPLY for item in messages)
    assert all(item["content"] != "0" + long_message for item in messages)


def test_交接单摘要与上下文脱敏_AC_32() -> None:
    raw_phone = "13800138000"
    raw_email = "alice@example.com"
    raw_id_card = "110101199001011234"
    content = f"转人工，电话{raw_phone}，邮箱 {raw_email}，身份证 {raw_id_card}"
    app = create_app()
    app.state.model_client = FakeModelClient({})
    with api_client(app) as api:
        login(api)
        assert send(api, content).status_code == 200

    handoff = only_handoff()
    serialized = json.dumps(
        {
            "summary": handoff.summary,
            "context": handoff.context,
            "pending_step": handoff.pending_step,
        },
        ensure_ascii=False,
    )
    for raw in (raw_phone, raw_email, raw_id_card):
        assert raw not in serialized
    assert "138****8000" in handoff.summary
    assert "a***@example.com" in handoff.summary
    assert "110101********1234" in handoff.summary
    assert "138****8000" in handoff.context["messages"][-1]["content"]


def test_摘要超过500字时截断_AC_32() -> None:
    content = "转人工" + "测" * 497
    assert len(content) == 500
    app = create_app()
    app.state.model_client = FakeModelClient({})
    with api_client(app) as api:
        login(api)
        assert send(api, content).status_code == 200

    handoff = only_handoff()
    assert len(handoff.summary) == 500
    assert handoff.summary.startswith("客户甲（customer_a）要求转人工")
    assert handoff.summary.endswith("测")


def test_排队中再次发送关键词不重复建单_AC_32() -> None:
    model = CountingModel()
    app = create_app()
    app.state.model_client = model
    with api_client(app) as api:
        login(api)
        first = send(api, "转人工")
        second = send(api, "转人工")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "QUEUED"
        assert [item["author_type"] for item in second.json()["messages"]] == ["customer"]

    assert model.calls == []
    assert len(rows(ServiceHandoff)) == 1
    assert [row.author_type for row in rows(ServiceMessage)] == [
        "customer",
        "system",
        "customer",
    ]


def test_模型失败交接单同样含完整上下文_AC_32() -> None:
    app = create_app()
    app.state.model_client = ErrorModel()
    with api_client(app) as api:
        login(api)
        assert send(api, "你好").status_code == 200
        second = send(api, "还在吗")
        assert second.status_code == 200
        assert second.json()["status"] == "QUEUED"

    handoff = only_handoff()
    assert handoff.reason == "MODEL_UNAVAILABLE"
    assert handoff.pending_step
    assert len(handoff.summary) <= 500
    assert "连续" in handoff.summary
    assert handoff.context["order_count"] == 0
    assert handoff.context["trigger"] == "model_error"
    assert handoff.context["customer_username"] == "customer_a"
    assert handoff.context["messages"][-1]["content"] == "还在吗"
    assert handoff.context["failure_count"] == 2
    assert handoff.context["last_error"] == "MODEL_ERROR"
    assert [item["status"] for item in handoff.context["ai_trace"][-2:]] == [
        "error",
        "error",
    ]
    assert all(item["event_type"] == "model" for item in handoff.context["ai_trace"][-2:])
