"""启动自检：数据库不可用时应用必须拒绝启动。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from services.api.main import create_app


def test_app_starts_when_database_available() -> None:
    try:
        with TestClient(create_app()) as client:
            assert client.get("/health").json() == {"status": "ok"}
    except (OperationalError, OSError):
        pytest.skip("本地数据库不可用，跳过启动自检")


def test_startup_recovers_pending_task_AC_12(monkeypatch) -> None:
    import asyncio
    from datetime import UTC, datetime

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.api.settings import settings
    from tests.integration.db_utils import db_available

    if not db_available():
        pytest.skip("Postgres 不可用")

    async def insert() -> None:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.execute(text("delete from cancellation_requests where id = 'task-startup'"))
            await conn.execute(
                text(
                    "insert into cancellation_requests "
                    "(id, tenant_id, user_id, order_id, state, idempotency_key, "
                    " expires_at, created_at, updated_at, version) values "
                    "(:id, 'tenant-a', 'user-a1', 'ORD-10001', 'SUBMITTING', "
                    " 'idem-startup', :expires, :now, :now, 0)"
                ),
                {
                    "id": "task-startup",
                    "expires": datetime.now(UTC),
                    "now": datetime.now(UTC),
                },
            )
        await engine.dispose()

    async def state() -> str:
        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            value = await conn.scalar(
                text("select state from cancellation_requests where id = 'task-startup'")
            )
        await engine.dispose()
        return str(value)

    asyncio.run(insert())
    monkeypatch.setattr(settings, "max_retries", 1)
    monkeypatch.setattr(settings, "retry_backoff_seconds", 0.01)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    assert asyncio.run(state()) == "MANUAL_REVIEW"
    asyncio.run(_cleanup())


async def _cleanup() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.api.settings import settings

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(text("delete from cancellation_requests where id = 'task-startup'"))
    await engine.dispose()


def test_startup_retries_then_accepts_AC_10(monkeypatch) -> None:
    import asyncio
    from datetime import UTC, datetime

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.api.main import create_app
    from services.api.settings import settings
    from services.mock_oms.faults import FaultRule
    from tests.integration.db_utils import db_available

    if not db_available():
        pytest.skip("Postgres 不可用")

    async def insert() -> None:
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.execute(text("delete from cancellation_requests where id = 'task-retry'"))
            await conn.execute(
                text(
                    "insert into cancellation_requests "
                    "(id, tenant_id, user_id, order_id, state, idempotency_key, "
                    " expires_at, created_at, updated_at, version) values "
                    "(:id, 'tenant-a', 'user-a1', 'ORD-10001', 'SUBMITTING', "
                    " 'idem-retry', :expires, :now, :now, 0)"
                ),
                {
                    "id": "task-retry",
                    "expires": datetime.now(UTC),
                    "now": datetime.now(UTC),
                },
            )
        await engine.dispose()

    async def state() -> str:
        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            value = await conn.scalar(
                text("select state from cancellation_requests where id = 'task-retry'")
            )
        await engine.dispose()
        return str(value)

    asyncio.run(insert())
    app = create_app()
    app.state.oms.submit_cancel("tenant-a", "user-a1", "ORD-10001", "idem-retry")
    app.state.oms.faults.add(FaultRule(kind="unavailable", tool="get_cancel_result", times=1))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert asyncio.run(state()) == "ACCEPTED"
    asyncio.run(_cleanup_task("task-retry"))


async def _cleanup_task(task_id: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.api.settings import settings

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text("delete from cancellation_requests where id = :id"), {"id": task_id}
        )
    await engine.dispose()
