"""多轮场景评测：脚本化模型下的查询、歧义澄清与取消意图（AC-01、AC-04、AC-08）。

场景只使用 FakeModelClient 与既有 create_app/MemoryRepository，不接真实模型或网络；
测试名带 AC 后缀，自动进入 evals/run.py 的聚合报告。
"""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.agent_runtime.model import FakeModelClient
from services.api.conversation_routes import get_repository
from services.api.main import create_app
from services.platform.models import AuditEvent, CancellationRequest, ToolExecution
from services.platform.settings import settings
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


class MemoryRepository:
    """只记录会话消息，避免多轮场景写开发库或依赖会话表。"""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str, str]] = []

    async def get_or_create(self, identity: Any, conversation_id: str | None) -> str:
        return conversation_id or "conv-eval"

    async def add_message(
        self, conversation_id: str, role: str, content: str, trace_id: str
    ) -> None:
        self.messages.append((conversation_id, role, content, trace_id))

    async def commit(self) -> None:
        return None


def make_api(model: FakeModelClient, repo: MemoryRepository) -> TestClient:
    app = create_app()
    app.state.model_client = model
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def login(api: TestClient) -> None:
    assert api.post("/session", json={"account_id": "zhang-ming"}).status_code == 200


def roles(repo: MemoryRepository) -> list[str]:
    return [role for _, role, _, _ in repo.messages]


async def cleanup_traces(trace_ids: list[str]) -> None:
    if not trace_ids:
        return
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            for model in (AuditEvent, ToolExecution, CancellationRequest):
                await session.execute(delete(model).where(model.trace_id.in_(trace_ids)))
            await session.commit()
    finally:
        await engine.dispose()


def test_多轮查询同一会话返回订单_AC_01() -> None:
    repo = MemoryRepository()
    model = FakeModelClient(
        {
            "查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"},
            "我的订单": {"intent": "QUERY_RECENT"},
        }
    )
    trace_ids: list[str] = []
    try:
        with make_api(model, repo) as api:
            login(api)
            first = api.post("/message", json={"content": "查 ORD-10001"}).json()
            trace_ids.append(first["trace_id"])
            assert first["orders"][0]["order_id"] == "ORD-10001"
            assert first["orders"][0]["status_text"] == "待发货"

            second = api.post(
                "/message",
                json={"content": "我的订单", "conversation_id": first["conversation_id"]},
            ).json()
            trace_ids.append(second["trace_id"])
            assert second["conversation_id"] == first["conversation_id"]
            assert "ORD-10001" in {order["order_id"] for order in second["orders"]}
            assert second["clarification"] == []
            assert first["trace_id"] != second["trace_id"]
            assert roles(repo) == ["user", "assistant", "user", "assistant"]
    finally:
        asyncio.run(cleanup_traces(trace_ids))


def test_多轮歧义澄清后查询指定订单_AC_08() -> None:
    repo = MemoryRepository()
    model = FakeModelClient(
        {
            "查 ORD-10001 和 ORD-10002": {"intent": "QUERY_ORDER"},
            "查 ORD-10002": {"intent": "QUERY_ORDER"},
        }
    )
    trace_ids: list[str] = []
    try:
        with make_api(model, repo) as api:
            login(api)
            first = api.post("/message", json={"content": "查 ORD-10001 和 ORD-10002"}).json()
            trace_ids.append(first["trace_id"])
            assert first["orders"] == []
            assert first["clarification"] == ["ORD-10001", "ORD-10002"]

            second = api.post(
                "/message",
                json={"content": "查 ORD-10002", "conversation_id": first["conversation_id"]},
            ).json()
            trace_ids.append(second["trace_id"])
            assert second["conversation_id"] == first["conversation_id"]
            assert second["clarification"] == []
            assert [order["order_id"] for order in second["orders"]] == ["ORD-10002"]
            assert roles(repo) == ["user", "assistant", "user", "assistant"]
    finally:
        asyncio.run(cleanup_traces(trace_ids))


def test_多轮取消意图沿同一trace确认_AC_04() -> None:
    repo = MemoryRepository()
    model = FakeModelClient(
        {
            "查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"},
            "取消 ORD-10001": {"intent": "CANCEL_ORDER", "order_id": "ORD-10001"},
        }
    )
    trace_ids: list[str] = []
    try:
        with make_api(model, repo) as api:
            login(api)
            queried = api.post("/message", json={"content": "查 ORD-10001"}).json()
            trace_ids.append(queried["trace_id"])
            assert queried["orders"][0]["order_id"] == "ORD-10001"

            started = api.post(
                "/message",
                json={"content": "取消 ORD-10001", "conversation_id": queried["conversation_id"]},
            ).json()
            trace_ids.append(started["trace_id"])
            assert started["conversation_id"] == queried["conversation_id"]
            card = started["cancellation"]
            assert card["state"] == "AWAITING_CONFIRMATION"
            assert card["order"]["order_id"] == "ORD-10001"
            assert card["trace_id"] == started["trace_id"]

            confirmed = api.post(f"/cancellation-requests/{card['task_id']}/confirm")
            assert confirmed.status_code == 200
            body = confirmed.json()
            assert body["state"] == "ACCEPTED"
            assert body["trace_id"] == started["trace_id"]
            assert roles(repo) == ["user", "assistant", "user", "assistant"]
    finally:
        asyncio.run(cleanup_traces(trace_ids))
