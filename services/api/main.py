"""Conversation API 的最小入口：健康检查与启动自检。"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.adapters.oms.factory import build_oms
from services.adapters.oms.mock import MockOmsAdapter
from services.agent_runtime.model import build_model_client
from services.api.account_routes import router as account_router
from services.api.admin_routes import router as admin_router
from services.api.audit import audit_transition
from services.api.auth_web import resolve_identity
from services.api.cancellation_routes import router as cancellation_router
from services.api.conversation_routes import router as conversation_router
from services.api.csrf import verify_origin
from services.api.handoff_routes import router as handoff_router
from services.api.session_routes import router as session_router
from services.domain.errors import ErrorCode
from services.platform.observability import AsyncTraceSink, TraceSinkError, use_trace_sink
from services.platform.settings import Settings, settings
from services.tools.cancel import build_cancel_gateway
from services.tools.gateway import error_envelope
from services.tools.query import build_query_gateway
from services.workflows.cancel import CancellationWorkflow, SqlCancellationRepository

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """JSON 行日志的 stdout 入口；已有 handler 时不重复添加。"""
    root = logging.getLogger()
    has_stdout = any(
        isinstance(handler, logging.StreamHandler)
        and getattr(handler, "stream", None) is sys.stdout
        for handler in root.handlers
    )
    if not has_stdout:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动时探测数据库；不可用则直接失败，不用重试掩盖配置错误。"""
    active: Settings = _app.state.settings
    engine = create_async_engine(active.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
        maker = async_sessionmaker(engine, expire_on_commit=False)

        async def recover() -> None:
            try:
                async with maker() as session:

                    async def audit(event: dict[str, object]) -> None:
                        await audit_transition(
                            session,
                            trace_id=str(event["trace_id"]),
                            identity=event["identity"],  # type: ignore[arg-type]
                            task_id=str(event["task_id"]),
                            order_id=str(event["order_id"]),
                            from_state=str(event["from_state"]),
                            to_state=str(event["to_state"]),
                            reason_code=event["reason_code"],  # type: ignore[arg-type]
                            result_status=str(event["result_status"]),
                            idempotency_key=event.get("idempotency_key"),  # type: ignore[arg-type]
                        )

                    workflow = CancellationWorkflow(
                        SqlCancellationRepository(session),
                        _app.state.cancel_gateway,
                        confirm_timeout_minutes=active.confirm_timeout_minutes,
                        max_retries=active.max_retries,
                        retry_backoff_seconds=active.retry_backoff_seconds,
                        audit=audit,
                    )
                    with use_trace_sink(AsyncTraceSink(maker)):
                        await workflow.recover_pending()
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
        close = getattr(_app.state.oms, "close", None)
        if callable(close):
            close()


def create_app(settings_override: Settings | None = None) -> FastAPI:
    configure_logging()
    active = settings_override or settings
    app = FastAPI(title="Customer Service Agent API", version="0.1.0", lifespan=lifespan)
    app.state.settings = active

    @app.exception_handler(TraceSinkError)
    async def _trace_sink_error(_request: Request, _error: TraceSinkError) -> JSONResponse:
        return JSONResponse(status_code=500, content=error_envelope(ErrorCode.INTERNAL_ERROR))

    app.state.oms = build_oms(active)
    app.state.model_client = build_model_client(active)
    app.state.query_gateway = build_query_gateway(app.state.oms)
    app.state.cancel_gateway = build_cancel_gateway(
        app.state.oms, timeout_seconds=active.oms_timeout_seconds
    )
    # 后添加的中间件先执行：先解析身份，再校验来源
    app.middleware("http")(verify_origin)
    app.middleware("http")(resolve_identity)
    app.include_router(session_router)
    app.include_router(conversation_router)
    app.include_router(cancellation_router)
    app.include_router(handoff_router)
    if active.test_accounts_enabled:
        app.include_router(account_router)
        if isinstance(app.state.oms, MockOmsAdapter):
            app.include_router(admin_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
