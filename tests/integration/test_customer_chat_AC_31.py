"""F-02：客户消息、AI 回复与模型失败自动转人工（AC-31）。"""

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.agent_runtime.model import FakeModelClient, ModelError
from backend.api.main import create_app
from backend.identity.customer_sessions import CUSTOMER_COOKIE
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
from backend.platform.settings import Settings, settings
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
    for username, display_name in (("customer_a", "客户甲"), ("customer_b", "客户乙")):
        db.add(
            ServiceCustomer(
                id=f"cust-{username}",
                tenant_id=settings.m1_tenant_id,
                username=username,
                password_hash=hash_password(DEMO_CREDENTIAL),
                display_name=display_name,
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


class SlowModel:
    async def respond(self, _message: str) -> Any:
        await asyncio.sleep(0.5)
        raise AssertionError("超时模型不应返回结果")


class ErrorModel:
    async def respond(self, _message: str) -> Any:
        raise ModelError("down")


def api_client(app: Any = None) -> TestClient:
    return TestClient(app or create_app())


def model_app(responses: dict[str, dict[str, Any]]) -> Any:
    app = create_app()
    app.state.model_client = FakeModelClient(responses)
    return app


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
        return list((await db.execute(select(model))).scalars())

    return asyncio.run(_with_db(read))


def set_conversation_status(conversation_id: str, status: str) -> None:
    async def write(db: Any) -> None:
        await db.execute(
            update(ServiceConversation)
            .where(ServiceConversation.id == conversation_id)
            .values(status=status)
        )
        await db.commit()

    asyncio.run(_with_db(write))


def test_普通消息落库并返回AI回复_AC_31() -> None:
    app = model_app(
        {
            "你好": {
                "intent": "UNKNOWN",
                "confidence": 0.95,
                "reply": "您好，请问有什么可以帮您？",
            }
        }
    )
    started = time.monotonic()
    with api_client(app) as api:
        login(api)
        response = send(api, "你好")
        elapsed = time.monotonic() - started
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "AI_ACTIVE"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "ai"]
        assert body["messages"][0]["content"] == "你好"
        assert body["messages"][1]["content"] == "您好，请问有什么可以帮您？"
        assert body["after_id"] == body["messages"][1]["id"]
        assert body["messages"][1]["created_at"].endswith("Z")

        polled = api.get("/customer/messages", params={"after_id": 0})
        assert polled.status_code == 200
        assert len(polled.json()["messages"]) == 2
        assert polled.json()["after_id"] == body["after_id"]

        session = api.get("/customer/session").json()
        assert session["conversation"]["after_id"] == body["after_id"]

        incremental = api.get(
            "/customer/messages", params={"after_id": body["messages"][0]["id"]}
        ).json()
        assert [item["author_type"] for item in incremental["messages"]] == ["ai"]

    assert elapsed < 10
    messages_table = rows(ServiceMessage)
    assert [(row.author_type, row.content) for row in messages_table] == [
        ("customer", "你好"),
        ("ai", "您好，请问有什么可以帮您？"),
    ]
    events = rows(ServiceAiEvent)
    assert len(events) == 1
    assert events[0].event_type == "model"
    assert events[0].status == "ok"
    assert events[0].confidence == 0.95
    assert rows(ServiceHandoff) == []


def test_模型超时自动转人工且只建一张单_AC_31() -> None:
    active = Settings(
        environment="development",
        customer_model_timeout_seconds=0.05,
        database_url=settings.database_url,
    )
    app = create_app(active)
    app.state.model_client = SlowModel()
    with api_client(app) as api:
        login(api)
        response = send(api, "你好")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "QUEUED"
        assert [item["author_type"] for item in body["messages"]] == ["customer", "system"]
        assert body["messages"][1]["content"] == "排队中，请稍候"

        again = send(api, "还在吗")
        assert again.status_code == 200
        assert again.json()["status"] == "QUEUED"
        assert [item["author_type"] for item in again.json()["messages"]] == ["customer"]

    handoffs = rows(ServiceHandoff)
    assert len(handoffs) == 1
    assert handoffs[0].status == "QUEUED"
    assert handoffs[0].reason == "MODEL_UNAVAILABLE"
    assert handoffs[0].context["order_count"] == 0
    events = rows(ServiceAiEvent)
    assert len(events) == 1
    assert events[0].status == "timeout"
    assert rows(ServiceConversation)[0].status == "QUEUED"
    assert [row.author_type for row in rows(ServiceMessage)] == [
        "customer",
        "system",
        "customer",
    ]


def test_模型异常自动转人工_AC_31() -> None:
    app = create_app()
    app.state.model_client = ErrorModel()
    with api_client(app) as api:
        login(api)
        response = send(api, "你好")
        assert response.status_code == 200
        assert response.json()["status"] == "QUEUED"
        assert response.json()["messages"][1]["content"] == "排队中，请稍候"

    assert rows(ServiceHandoff)[0].reason == "MODEL_UNAVAILABLE"
    assert rows(ServiceAiEvent)[0].status == "error"


def test_未登录与非法消息被拒绝_AC_31() -> None:
    with api_client() as api:
        assert api.post("/customer/messages", json={"content": "你好"}).status_code == 401
        assert api.get("/customer/messages").status_code == 401

        login(api)
        empty = api.post("/customer/messages", json={"content": ""})
        blank = api.post("/customer/messages", json={"content": "   "})
        too_long = api.post("/customer/messages", json={"content": "x" * 501})
        extra = api.post("/customer/messages", json={"content": "你好", "conversation_id": "other"})

    assert empty.status_code == 422
    assert empty.json()["code"] == "VALIDATION_ERROR"
    assert blank.status_code == 422
    assert too_long.status_code == 422
    assert extra.status_code == 422
    assert rows(ServiceMessage) == []


def test_关闭会话写消息返回409_AC_31() -> None:
    with api_client() as api:
        login(api)
        conversation_id = api.get("/customer/session").json()["conversation"]["id"]
        set_conversation_status(conversation_id, "CLOSED")

        response = send(api, "你好")
        assert response.status_code == 409
        assert response.json()["code"] == "CONVERSATION_CLOSED"
        history = api.get("/customer/messages")
        assert history.status_code == 200
        assert history.json()["status"] == "CLOSED"

    assert rows(ServiceMessage) == []


def test_刷新与重新登录恢复消息历史_AC_31() -> None:
    app = model_app(
        {
            "你好": {
                "intent": "UNKNOWN",
                "confidence": 0.9,
                "reply": "您好，我是 AI 客服。",
            }
        }
    )
    with api_client(app) as api:
        login(api)
        first = send(api, "你好").json()
        conversation_id = first["conversation_id"]
        token = api.cookies.get(CUSTOMER_COOKIE)

        login(api)
        assert api.cookies.get(CUSTOMER_COOKIE) != token
        history = api.get("/customer/messages", params={"after_id": 0}).json()
        assert history["conversation_id"] == conversation_id
        assert len(history["messages"]) == 2
        assert history["after_id"] == first["after_id"]

        empty = api.get("/customer/messages", params={"after_id": history["after_id"]}).json()
        assert empty["messages"] == []
        assert empty["after_id"] == history["after_id"]


def test_模型默认超时为10秒_AC_31() -> None:
    field = Settings.model_fields["customer_model_timeout_seconds"]
    assert field.default == 10.0


def test_同一幂等键重试不重复落库与调模型_AC_31() -> None:
    calls: list[str] = []

    class CountingModel:
        async def respond(self, message: str) -> Any:
            from backend.agent_runtime.model import ChatReply

            calls.append(message)
            return ChatReply(intent="UNKNOWN", confidence=0.9, reply="您好。")

    app = create_app()
    app.state.model_client = CountingModel()
    with api_client(app) as api:
        login(api)
        first = send(api, "你好", key="idem-1")
        second = send(api, "你好", key="idem-1")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["messages"] == first.json()["messages"]
        assert second.json()["after_id"] == first.json()["after_id"]

        missing = api.post("/customer/messages", json={"content": "没有幂等键"})
        assert missing.status_code == 422
        assert missing.json()["code"] == "VALIDATION_ERROR"

    assert calls == ["你好"]
    assert [row.author_type for row in rows(ServiceMessage)] == ["customer", "ai"]


def test_长请求关联标识不会写爆trace列_基座豁免() -> None:
    app = model_app({"你好": {"intent": "UNKNOWN", "confidence": 0.9, "reply": "您好。"}})
    with api_client(app) as api:
        login(api)
        response = api.post(
            "/customer/messages",
            json={"content": "你好"},
            headers={
                "Idempotency-Key": "idem-long-trace",
                "X-Request-ID": "x" * 37,
            },
        )
        assert response.status_code == 200, response.text
        assert response.headers["X-Request-ID"] != "x" * 37
        assert len(response.headers["X-Request-ID"]) <= 36
    assert len(rows(ServiceMessage)[0].trace_id) <= 36


def test_发消息时AI空闲24h惰性关闭并新建会话_AC_31() -> None:
    app = model_app({"你好": {"intent": "UNKNOWN", "confidence": 0.9, "reply": "您好。"}})
    with api_client(app) as api:
        login(api)
        old_id = api.get("/customer/session").json()["conversation"]["id"]

        async def age(db: Any) -> None:
            await db.execute(
                update(ServiceConversation)
                .where(ServiceConversation.id == old_id)
                .values(last_activity_at=datetime.now(UTC) - timedelta(hours=25))
            )
            await db.commit()

        asyncio.run(_with_db(age))
        response = send(api, "你好")
        assert response.status_code == 200
        new_id = response.json()["conversation_id"]
        assert new_id != old_id

    conversations = {row.id: row for row in rows(ServiceConversation)}
    assert conversations[old_id].status == "CLOSED"
    assert conversations[new_id].status == "AI_ACTIVE"


def test_客户之间的消息互相隔离_AC_31() -> None:
    app = model_app(
        {
            "你好": {"intent": "UNKNOWN", "confidence": 0.9, "reply": "您好。"},
            "在吗": {"intent": "UNKNOWN", "confidence": 0.9, "reply": "在的。"},
        }
    )
    with api_client(app) as api:
        login(api, "customer_a")
        a = send(api, "你好").json()
        login(api, "customer_b")
        b_history = api.get("/customer/messages", params={"after_id": 0}).json()
        assert b_history["messages"] == []
        b = send(api, "在吗").json()
        assert b["conversation_id"] != a["conversation_id"]
        assert [item["content"] for item in b["messages"]] == ["在吗", "在的。"]

    assert len(rows(ServiceConversation)) == 2
    assert len(rows(ServiceMessage)) == 4
