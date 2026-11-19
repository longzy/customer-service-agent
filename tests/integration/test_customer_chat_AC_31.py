"""F-02/F-24：客户消息、AI 回复与模型失败分级降级（AC-31）。"""

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from backend.agent_runtime.model import FakeModelClient, ModelError
from backend.api.main import create_app
from backend.conversations.customer_chat import (
    MODEL_FAILURE_HANDOFF_NOTICE,
    RETRY_NOTICE,
)
from backend.identity.customer_sessions import CUSTOMER_COOKIE
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceHandoff,
    ServiceMessage,
)
from backend.platform.settings import Settings, settings
from tests.integration.customer_support import (
    cleanup_customer_db,
    login_customer,
    prepare_customer_db,
    rows_of,
    with_db,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


class SlowModel:
    async def respond(self, _message: str) -> Any:
        await asyncio.sleep(0.5)
        raise AssertionError("超时模型不应返回结果")


class ErrorModel:
    async def respond(self, _message: str) -> Any:
        raise ModelError("down")


class FlakyModel:
    """可在成功/失败之间切换，用于验证成功回复后失败计数清零。"""

    def __init__(self) -> None:
        self.failing = True

    async def respond(self, _message: str) -> Any:
        if self.failing:
            raise ModelError("down")
        from backend.agent_runtime.model import ChatReply

        return ChatReply(intent="UNKNOWN", confidence=0.95, reply="您好，请问有什么可以帮您？")


def api_client(app: Any = None) -> TestClient:
    return TestClient(app or create_app())


def model_app(responses: dict[str, dict[str, Any]]) -> Any:
    app = create_app()
    app.state.model_client = FakeModelClient(responses)
    return app


def login(api: TestClient, username: str = "customer_a") -> Any:
    return login_customer(api, username)


def send(api: TestClient, content: str, key: str | None = None) -> Any:
    return api.post(
        "/customer/messages",
        json={"content": content},
        headers={"Idempotency-Key": key or f"test-{uuid.uuid4()}"},
    )


def rows(model: Any) -> list[Any]:
    return rows_of(model)


def set_conversation_status(conversation_id: str, status: str) -> None:
    async def write(db: Any) -> None:
        await db.execute(
            update(ServiceConversation)
            .where(ServiceConversation.id == conversation_id)
            .values(status=status)
        )
        await db.commit()

    asyncio.run(with_db(write))


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


def test_模型超时单次提示重试且连续两次转人工_AC_31() -> None:
    active = Settings(
        environment="development",
        customer_model_timeout_seconds=0.05,
        database_url=settings.database_url,
    )
    app = create_app(active)
    app.state.model_client = SlowModel()
    with api_client(app) as api:
        login(api)
        first = send(api, "你好")
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "AI_ACTIVE"
        assert [item["author_type"] for item in first.json()["messages"]] == [
            "customer",
            "system",
        ]
        assert first.json()["messages"][1]["content"] == RETRY_NOTICE

        second = send(api, "还在吗")
        assert second.status_code == 200, second.text
        assert second.json()["status"] == "QUEUED"
        assert [item["author_type"] for item in second.json()["messages"]] == [
            "customer",
            "system",
        ]
        assert second.json()["messages"][1]["content"] == MODEL_FAILURE_HANDOFF_NOTICE

        queued = send(api, "有人吗")
        assert queued.status_code == 200
        assert queued.json()["status"] == "QUEUED"
        assert [item["author_type"] for item in queued.json()["messages"]] == ["customer"]

    handoffs = rows(ServiceHandoff)
    assert len(handoffs) == 1
    assert handoffs[0].status == "QUEUED"
    assert handoffs[0].reason == "MODEL_UNAVAILABLE"
    assert handoffs[0].context["order_count"] == 0
    assert handoffs[0].context["failure_count"] == 2
    assert handoffs[0].context["last_error"] == "MODEL_TIMEOUT"
    events = rows(ServiceAiEvent)
    assert len(events) == 2
    assert {event.status for event in events} == {"timeout"}
    assert rows(ServiceConversation)[0].status == "QUEUED"
    assert [row.author_type for row in rows(ServiceMessage)] == [
        "customer",
        "system",
        "customer",
        "system",
        "customer",
    ]


def test_模型异常单次提示重试_AC_31() -> None:
    app = create_app()
    app.state.model_client = ErrorModel()
    with api_client(app) as api:
        login(api)
        first = send(api, "你好")
        assert first.status_code == 200
        assert first.json()["status"] == "AI_ACTIVE"
        assert first.json()["messages"][1]["content"] == RETRY_NOTICE
        assert rows(ServiceHandoff) == []
        assert rows(ServiceConversation)[0].status == "AI_ACTIVE"

        second = send(api, "还在吗")
        assert second.status_code == 200
        assert second.json()["status"] == "QUEUED"
        assert second.json()["messages"][1]["content"] == MODEL_FAILURE_HANDOFF_NOTICE

    handoff = rows(ServiceHandoff)[0]
    assert handoff.reason == "MODEL_UNAVAILABLE"
    assert handoff.context["failure_count"] == 2
    assert handoff.context["last_error"] == "MODEL_ERROR"
    assert {event.status for event in rows(ServiceAiEvent)} == {"error"}


def test_模型失败后成功回复清零_AC_31() -> None:
    model = FlakyModel()
    app = create_app()
    app.state.model_client = model
    with api_client(app) as api:
        login(api)
        assert send(api, "你好").json()["messages"][1]["content"] == RETRY_NOTICE

        model.failing = False
        recovered = send(api, "在吗")
        assert recovered.json()["status"] == "AI_ACTIVE"
        assert [item["author_type"] for item in recovered.json()["messages"]] == [
            "customer",
            "ai",
        ]

        model.failing = True
        third = send(api, "又断了")
        assert third.json()["status"] == "AI_ACTIVE"
        assert third.json()["messages"][1]["content"] == RETRY_NOTICE

    assert rows(ServiceHandoff) == []
    events = sorted(rows(ServiceAiEvent), key=lambda event: event.created_at)
    assert [event.status for event in events] == ["error", "ok", "error"]
    assert rows(ServiceConversation)[0].status == "AI_ACTIVE"


def test_连续失败可混合超时与异常_AC_31() -> None:
    active = Settings(
        environment="development",
        customer_model_timeout_seconds=0.05,
        database_url=settings.database_url,
    )
    app = create_app(active)
    app.state.model_client = SlowModel()
    with api_client(app) as api:
        login(api)
        assert send(api, "你好").json()["status"] == "AI_ACTIVE"
        app.state.model_client = ErrorModel()
        second = send(api, "还在吗")
        assert second.json()["status"] == "QUEUED"
        assert second.json()["messages"][1]["content"] == MODEL_FAILURE_HANDOFF_NOTICE

    handoff = rows(ServiceHandoff)[0]
    assert handoff.context["failure_count"] == 2
    assert handoff.context["last_error"] == "MODEL_ERROR"
    events = sorted(rows(ServiceAiEvent), key=lambda event: event.created_at)
    assert [event.status for event in events] == ["timeout", "error"]


def simulate_return_to_ai(conversation_id: str) -> None:
    """用数据库状态模拟 F-12 的转回：会话回 AI_ACTIVE、旧单关闭、写转回系统消息。"""

    async def write(db: Any) -> None:
        await db.execute(
            update(ServiceConversation)
            .where(ServiceConversation.id == conversation_id)
            .values(status="AI_ACTIVE", assigned_employee_id=None)
        )
        await db.execute(
            update(ServiceHandoff)
            .where(ServiceHandoff.conversation_id == conversation_id)
            .values(status="CLOSED")
        )
        db.add(
            ServiceMessage(
                conversation_id=conversation_id,
                author_type="system",
                author_id=None,
                content="已转回 AI 客服",
                idempotency_key=None,
                trace_id="trace-return",
                created_at=datetime.now(UTC),
            )
        )
        await db.commit()

    asyncio.run(with_db(write))


def test_转回AI后首次失败不沿用旧计数_AC_31() -> None:
    app = create_app()
    app.state.model_client = ErrorModel()
    with api_client(app) as api:
        login(api)
        first = send(api, "你好")
        conversation_id = first.json()["conversation_id"]
        assert send(api, "还在吗").json()["status"] == "QUEUED"
        simulate_return_to_ai(conversation_id)

        retry = send(api, "我又来了")
        assert retry.json()["status"] == "AI_ACTIVE"
        assert retry.json()["messages"][1]["content"] == RETRY_NOTICE

        again = send(api, "又断了")
        assert again.json()["status"] == "QUEUED"

    handoffs = sorted(rows(ServiceHandoff), key=lambda handoff: handoff.created_at)
    assert len(handoffs) == 2
    assert handoffs[0].status == "CLOSED"
    assert handoffs[1].context["failure_count"] == 2
    assert handoffs[1].context["last_error"] == "MODEL_ERROR"


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


def test_交接单open状态与plan一致_AC_31() -> None:
    from backend.conversations.statuses import OPEN_HANDOFF_STATUSES

    assert OPEN_HANDOFF_STATUSES == ("QUEUED", "CLAIMED", "ACTIVE")


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

        asyncio.run(with_db(age))
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
