"""人工转接：上下文组装与停止自动回复（AC-13）。"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from services.api.auth import Identity
from services.api.db import session_factory
from services.api.handoff import create_handoff
from services.api.main import create_app
from services.api.models import (
    CancellationRequest,
    Conversation,
    Handoff,
    Message,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

OWNER = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")


async def test_交接上下文包含消息与任务_AC_13() -> None:
    async with session_factory() as session:
        await session.execute(delete(Handoff).where(Handoff.conversation_id == "conv-h"))
        await session.execute(delete(Message).where(Message.conversation_id == "conv-h"))
        await session.execute(delete(CancellationRequest).where(CancellationRequest.id == "task-h"))
        await session.execute(delete(Conversation).where(Conversation.id == "conv-h"))
        await session.commit()
        session.add(
            Conversation(id="conv-h", tenant_id="tenant-a", user_id="user-a1", channel="web")
        )
        session.add(
            Message(
                id="m-h1",
                conversation_id="conv-h",
                role="user",
                content="取消 ORD-10001",
                trace_id="t-h",
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            CancellationRequest(
                id="task-h",
                tenant_id="tenant-a",
                user_id="user-a1",
                order_id="ORD-10001",
                state="AWAITING_CONFIRMATION",
                idempotency_key="idem-h",
                conversation_id="conv-h",
                expires_at=datetime.now(UTC),
            )
        )
        await session.commit()

        handoff = await create_handoff(session, OWNER, "conv-h", "trace-h")
        assert "取消 ORD-10001" in handoff.summary
        assert handoff.context["orders"] == ["ORD-10001"]
        assert handoff.context["workflow_state"] == "AWAITING_CONFIRMATION"
        assert handoff.context["pending_step"] == "等待用户确认取消"

        await session.execute(delete(Handoff).where(Handoff.conversation_id == "conv-h"))
        await session.execute(delete(Message).where(Message.conversation_id == "conv-h"))
        await session.execute(delete(CancellationRequest).where(CancellationRequest.id == "task-h"))
        await session.execute(delete(Conversation).where(Conversation.id == "conv-h"))
        await session.commit()


def test_转人工后消息被拒绝_AC_13() -> None:
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.api.settings import settings

    async def setup() -> None:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.execute(text("delete from handoffs where conversation_id = 'conv-x'"))
            await conn.execute(text("delete from conversations where id = 'conv-x'"))
            await conn.execute(
                text(
                    "insert into conversations "
                    "(id, tenant_id, user_id, channel, created_at, updated_at) "
                    "values ('conv-x', 'tenant-a', 'user-a1', 'web', now(), now())"
                )
            )
            await conn.execute(
                text(
                    "insert into handoffs "
                    "(id, conversation_id, tenant_id, user_id, summary, context, "
                    " trace_id, created_at) "
                    "values ('h-x', 'conv-x', 'tenant-a', 'user-a1', 's', '{}', 't', now())"
                )
            )
        await engine.dispose()

    async def cleanup() -> None:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.execute(text("delete from handoffs where conversation_id = 'conv-x'"))
            await conn.execute(text("delete from conversations where id = 'conv-x'"))
        await engine.dispose()

    asyncio.run(setup())
    with TestClient(create_app()) as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        response = api.post("/message", json={"content": "在吗", "conversation_id": "conv-x"})
        assert response.status_code == 409
    asyncio.run(cleanup())


def test_handoff_api_context_and_idempotent_AC_13() -> None:
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.agent_runtime.model import FakeModelClient
    from services.api.settings import settings

    async def cleanup() -> None:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "delete from handoffs where conversation_id in "
                    "(select id from conversations where user_id = 'user-a1' "
                    "and created_at > now() - interval '1 minute')"
                )
            )
            await conn.execute(
                text(
                    "delete from messages where conversation_id in "
                    "(select id from conversations where user_id = 'user-a1' "
                    "and created_at > now() - interval '1 minute')"
                )
            )
            await conn.execute(
                text(
                    "delete from conversations where user_id = 'user-a1' "
                    "and created_at > now() - interval '1 minute'"
                )
            )
        await engine.dispose()

    asyncio.run(cleanup())
    app = create_app()
    app.state.model_client = FakeModelClient(
        {"查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"}}
    )
    with TestClient(app) as api:
        api.post("/session", json={"account_id": "zhang-ming"})
        message = api.post("/message", json={"content": "查 ORD-10001"}).json()
        conversation_id = message["conversation_id"]

        first = api.post("/handoff", json={"conversation_id": conversation_id})
        assert first.status_code == 201
        assert first.json()["context"]["orders"] == ["ORD-10001"]

        second = api.post("/handoff", json={"conversation_id": conversation_id})
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]

        api.post("/session", json={"account_id": "li-hua"})
        assert api.post("/handoff", json={"conversation_id": conversation_id}).status_code == 404
    asyncio.run(cleanup())
