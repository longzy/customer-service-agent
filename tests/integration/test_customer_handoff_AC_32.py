"""F-03：关键词转人工与完整交接单（AC-32）。

- 4 个关键词及空白/标点变体命中后不调用模型，直接入队并写完整交接单。
- 交接单：摘要 ≤500、最近 20 条且正文 ≤4000 字、AI 轨迹、原因、待办、脱敏、order_count=0。
- 模型失败路径复用同一构造，避免出现两套交接单上下文。
"""

import asyncio
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.agent_runtime.model import DEFAULT_FAKE_REPLY, ChatReply, FakeModelClient, ModelError
from backend.api.main import create_app
from backend.identity.passwords import hash_password
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceCustomer,
    ServiceCustomerSession,
    ServiceHandoff,
    ServiceMessage,
    ServiceRateLimitBucket,
)
from backend.platform.settings import settings
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

DEMO_CREDENTIAL = "demo-login-value"


async def _with_db(action: Any) -> Any:
    engine = create_async_engine(settings.database_url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            return await action(db)
    finally:
        await engine.dispose()


async def _reset(db: Any) -> None:
    await db.execute(delete(ServiceMessage))
    await db.execute(delete(ServiceAiEvent))
    await db.execute(delete(ServiceHandoff))
    await db.execute(delete(ServiceCustomerSession))
    await db.execute(delete(ServiceConversation))
    await db.execute(delete(ServiceCustomer))
    await db.execute(delete(ServiceRateLimitBucket))
    await db.commit()


async def _seed(db: Any) -> None:
    # F-25 起种子客户与 OMS 身份绑定，转人工时才能带真实订单上下文（F-28）。
    for username, display_name, oms_customer_id in (
        ("customer_a", "客户甲", "user-a1"),
        ("customer_b", "客户乙", "user-b1"),
    ):
        db.add(
            ServiceCustomer(
                id=f"cust-{username}",
                tenant_id=settings.m1_tenant_id,
                username=username,
                password_hash=hash_password(DEMO_CREDENTIAL),
                display_name=display_name,
                oms_customer_id=oms_customer_id,
                active=True,
            )
        )
    await db.commit()


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    asyncio.run(_with_db(_reset))
    asyncio.run(_with_db(_seed))
    yield
    asyncio.run(_with_db(_reset))


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


def rows(model: Any) -> list[Any]:
    async def read(db: Any) -> list[Any]:
        # 按主键排序：DELETE/INSERT 后 seq scan 顺序不稳定，消息顺序断言会抖动
        return list((await db.execute(select(model).order_by(model.id))).scalars())

    return asyncio.run(_with_db(read))


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
    trace_types = [item["event_type"] for item in trace]
    # 同一请求内写两条事件，库表没有序列列，轨迹顺序不承诺（既有行为）：
    # 只断言两类事件各一条，且都只有元数据。
    assert trace_types.count("intent") == 1
    assert trace_types.count("order_query") == 1
    intent_event = next(item for item in trace if item["event_type"] == "intent")
    order_event = next(item for item in trace if item["event_type"] == "order_query")
    assert intent_event["status"] == "matched"
    assert order_event["status"] == "ok"
    assert "reply" not in order_event

    events = rows(ServiceAiEvent)
    assert sorted((event.event_type, event.status) for event in events) == [
        ("intent", "matched"),
        ("order_query", "ok"),
    ]
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
    assert trace_types.count("intent") == 1
    assert trace_types.count("order_query") == 1
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
