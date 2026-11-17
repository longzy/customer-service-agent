"""Conversation API 的最小入口：健康检查与启动自检。"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.adapters.oms.factory import build_oms
from backend.adapters.oms.mock import MockOmsAdapter
from backend.agent_runtime.model import build_model_client
from backend.api.account_routes import router as account_router
from backend.api.admin_routes import router as admin_router
from backend.api.audit import audit_transition
from backend.api.auth_web import resolve_identity
from backend.api.cancellation_routes import router as cancellation_router
from backend.api.conversation_routes import router as conversation_router
from backend.api.csrf import verify_origin
from backend.api.customer_routes import router as customer_router
from backend.api.errors import ApiError, api_error_handler
from backend.api.handoff_routes import router as handoff_router
from backend.api.request_id import attach_request_id
from backend.api.session_routes import router as session_router
from backend.domain.errors import ErrorCode
from backend.platform.observability import AsyncTraceSink, TraceSinkError, use_trace_sink
from backend.platform.settings import Settings, settings
from backend.tools.cancel import build_cancel_gateway
from backend.tools.gateway import error_envelope
from backend.tools.query import build_query_gateway
from backend.workflows.cancel import CancellationWorkflow, SqlCancellationRepository

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

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, error: ApiError) -> JSONResponse:
        return await api_error_handler(request, error)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, error: RequestValidationError) -> Response:
        # 只有新 M1 客户 API 使用统一封套；旧 M1-P 路由保持原响应格式。
        if request.url.path.startswith("/customer/"):
            return JSONResponse(status_code=422, content=error_envelope(ErrorCode.VALIDATION_ERROR))
        return await request_validation_exception_handler(request, error)

    @app.exception_handler(Exception)
    async def _unhandled_error(request: Request, error: Exception) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", None)
        logger.exception("未处理异常 trace_id=%s", trace_id, exc_info=error)
        headers = {"X-Request-ID": trace_id} if trace_id else None
        return JSONResponse(
            status_code=500,
            content=error_envelope(ErrorCode.INTERNAL_ERROR),
            headers=headers,
        )

    app.state.oms = build_oms(active)
    app.state.model_client = build_model_client(active)
    app.state.query_gateway = build_query_gateway(app.state.oms)
    app.state.cancel_gateway = build_cancel_gateway(
        app.state.oms, timeout_seconds=active.oms_timeout_seconds
    )
    # 后添加的中间件先执行：请求关联标识最外层，最后解析身份、校验来源
    app.middleware("http")(verify_origin)
    app.middleware("http")(resolve_identity)
    app.middleware("http")(attach_request_id)
    if active.m1_enabled:
        app.include_router(customer_router)
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
