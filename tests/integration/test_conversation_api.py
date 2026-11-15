"""Conversation API：认证、查询落库与模型错误（AC-01、AC-08）。"""

from typing import Any

from fastapi.testclient import TestClient

from services.agent_runtime.model import FakeModelClient
from services.api.conversation_routes import get_repository
from services.api.main import create_app


class MemoryRepository:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str, str]] = []
        self.committed = False

    async def get_or_create(self, identity: Any, conversation_id: str | None) -> str:
        return conversation_id or "conv-1"

    async def add_message(
        self, conversation_id: str, role: str, content: str, trace_id: str
    ) -> None:
        self.messages.append((conversation_id, role, content, trace_id))

    async def commit(self) -> None:
        self.committed = True


def test_未登录不能发消息_AC_01() -> None:
    with TestClient(create_app()) as api:
        assert api.post("/message", json={"content": "查 ORD-10001"}).status_code == 401


def test_查询订单返回结果并落库_AC_01() -> None:
    repo = MemoryRepository()
    app = create_app()
    app.state.model_client = FakeModelClient(
        {"查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}}
    )
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as api:
        assert api.post("/session", json={"account_id": "zhang-ming"}).status_code == 200
        response = api.post("/message", json={"content": "查 ORD-10001"})
        assert response.status_code == 200
        body = response.json()
        assert body["orders"][0]["order_id"] == "ORD-10001"
        assert body["clarification"] == []
        assert [role for _, role, _, _ in repo.messages] == ["user", "assistant"]
        assert repo.committed is True


def test_多候选返回澄清_AC_08() -> None:
    repo = MemoryRepository()
    app = create_app()
    app.state.model_client = FakeModelClient(
        {"查 ORD-10001 和 ORD-10002": {"intent": "QUERY_ORDER"}}
    )
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        body = api.post("/message", json={"content": "查 ORD-10001 和 ORD-10002"}).json()
        assert body["orders"] == []
        assert body["clarification"] == ["ORD-10001", "ORD-10002"]


def test_模型不可用返回503且不写助手消息_AC_01() -> None:
    repo = MemoryRepository()
    app = create_app()

    class Broken:
        async def classify(self, message: str) -> dict[str, Any]:
            from services.agent_runtime.model import ModelError

            raise ModelError("down")

    app.state.model_client = Broken()
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        response = api.post("/message", json={"content": "查 ORD-10001"})
        assert response.status_code == 503
        assert [role for _, role, _, _ in repo.messages] == ["user"]
