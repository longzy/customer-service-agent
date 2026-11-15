"""Conversation API：认证、查询落库与模型错误（AC-01、AC-08）。"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from services.agent_runtime.model import FakeModelClient
from services.api.conversation_routes import get_repository
from services.api.main import create_app
from services.tools.query import build_query_gateway
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


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


def test_未登录不能发消息_AC_20() -> None:
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
        assert body["orders"][0]["status_text"] == "待发货"
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


def test_模型不可用返回503且保留用户消息_基座豁免() -> None:
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
        assert repo.committed is True, "模型失败时也应保留用户消息"


def test_非法模型输出返回503并保留用户消息_基座豁免() -> None:
    repo = MemoryRepository()
    app = create_app()
    app.state.model_client = FakeModelClient({"查单": {"intent": "NOT_AN_INTENT"}})
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        response = api.post("/message", json={"content": "查单"})
        assert response.status_code == 503
        assert [role for _, role, _, _ in repo.messages] == ["user"]
        assert repo.committed is True


def test_最近订单故障返回可见文案_AC_01() -> None:
    from services.mock_oms.faults import FaultRule

    repo = MemoryRepository()
    app = create_app()
    app.state.model_client = FakeModelClient({"我的订单": {"intent": "QUERY_RECENT"}})
    app.state.query_gateway = build_query_gateway(app.state.oms)
    app.state.oms.faults.add(FaultRule(kind="unavailable", tool="list_recent_orders"))
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        body = api.post("/message", json={"content": "我的订单"}).json()
        assert body["orders"] == []
        assert "服务暂时不可用" in body["reply"]


def test_取消意图返回确认卡片_AC_04() -> None:
    repo = MemoryRepository()
    app = create_app()
    app.state.model_client = FakeModelClient(
        {"取消 ORD-10001": {"intent": "CANCEL_ORDER", "order_id": "ORD-10001"}}
    )
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        body = api.post("/message", json={"content": "取消 ORD-10001"}).json()
        card = body["cancellation"]
        assert card["state"] == "AWAITING_CONFIRMATION"
        assert card["state_text"] == "等待您确认"
        assert card["order"]["order_id"] == "ORD-10001"
        assert card["order"]["status_text"] == "待发货"
        assert card["order"]["amount_cents"] == 39900
