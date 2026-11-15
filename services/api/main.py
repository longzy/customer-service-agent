"""Conversation API 的最小入口：健康检查与启动自检。"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.agent_runtime.model import build_model_client
from services.api.account_routes import router as account_router
from services.api.admin_routes import router as admin_router
from services.api.auth import resolve_identity
from services.api.cancellation_routes import router as cancellation_router
from services.api.conversation_routes import router as conversation_router
from services.api.session_routes import router as session_router
from services.api.settings import settings
from services.mock_oms.service import MockOms
from services.tools.cancel import build_cancel_gateway
from services.tools.query import build_query_gateway
from services.workflows.cancel import CancellationWorkflow, SqlCancellationRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动时探测数据库；不可用则直接失败，不用重试掩盖配置错误。"""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async def recover() -> None:
            try:
                async with maker() as session:
                    workflow = CancellationWorkflow(
                        SqlCancellationRepository(session),
                        _app.state.cancel_gateway,
                        confirm_timeout_minutes=settings.confirm_timeout_minutes,
                        max_retries=settings.max_retries,
                        retry_backoff_seconds=settings.retry_backoff_seconds,
                    )
                    await workflow.recover_pending(f"startup-{uuid4()}")
            except Exception:  # noqa: BLE001 - 恢复失败不应阻止服务启动
                logger.exception("启动恢复失败")

        task = asyncio.create_task(recover())
        yield
        try:
            await asyncio.wait_for(task, timeout=30)
        except TimeoutError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Customer Service Agent API", version="0.1.0", lifespan=lifespan)
    app.state.oms = MockOms()
    app.state.model_client = build_model_client(settings)
    app.state.query_gateway = build_query_gateway(app.state.oms)
    app.state.cancel_gateway = build_cancel_gateway(
        app.state.oms, timeout_seconds=settings.oms_timeout_seconds
    )
    app.middleware("http")(resolve_identity)
    app.include_router(session_router)
    app.include_router(conversation_router)
    app.include_router(cancellation_router)
    if settings.test_accounts_enabled:
        app.include_router(admin_router)
        app.include_router(account_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
