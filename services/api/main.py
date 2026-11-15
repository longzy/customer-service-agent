"""Conversation API 的最小入口：健康检查与启动自检。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.admin_routes import router as admin_router
from services.api.auth import resolve_identity
from services.api.session_routes import router as session_router
from services.api.settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动时探测数据库；不可用则直接失败，不用重试掩盖配置错误。"""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    finally:
        await engine.dispose()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Customer Service Agent API", version="0.1.0", lifespan=lifespan)
    app.middleware("http")(resolve_identity)
    app.include_router(session_router)
    if settings.environment != "production":
        app.include_router(admin_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
