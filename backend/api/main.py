"""Conversation API 的最小入口：健康检查与启动自检。"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from backend.adapters.oms.factory import build_oms
from backend.adapters.oms.mock import MockOmsAdapter
from backend.agent_runtime.model import build_model_client
from backend.api.admin_routes import router as admin_router
from backend.api.csrf import verify_origin
from backend.api.errors import ApiError, api_error_handler
from backend.api.recovery import recover_cancellations
from backend.api.request_id import attach_request_id
from backend.api.service_audit import audit_api_error
from backend.audit import SqlAuditWriter
from backend.conversations.customer_http import router as customer_router
from backend.conversations.workspace_http import router as workspace_router
from backend.domain.errors import ErrorCode
from backend.identity.http import router as employee_router
from backend.platform import metrics
from backend.platform.db import engine, session_factory, trace_engine, trace_session_factory
from backend.platform.observability import (
    AuditWriteError,
    BufferedTraceSink,
    SampledTraceSink,
    use_trace_sink,
)
from backend.platform.retention import cleanup
from backend.platform.settings import Settings, settings
from backend.tools.cancel import build_cancel_gateway
from backend.tools.gateway import error_envelope
from backend.tools.query import build_query_gateway

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
    async with engine.connect() as connection:
        await connection.execute(text("select 1"))

    trace_sink = BufferedTraceSink(
        trace_session_factory,
        buffer_size=active.trace_buffer_size,
        flush_interval_ms=active.trace_flush_interval_ms,
        batch_size=active.trace_batch_size,
    )
    _app.state.trace_sink = trace_sink

    async def recover() -> None:
        try:
            async with session_factory() as session:
                with use_trace_sink(trace_sink):
                    await recover_cancellations(
                        session,
                        gateway=_app.state.cancel_gateway,
                        audit_writer=_app.state.audit_writer,
                        active=active,
                    )
        except Exception:  # noqa: BLE001 - 恢复失败不应阻止服务启动
            logger.exception("启动恢复失败")

    async def retention_loop() -> None:
        while True:
            await asyncio.sleep(max(active.retention_interval_seconds, 60))
            try:
                report = await cleanup(
                    session_factory,
                    apply=True,
                    trace_retention_days=active.trace_retention_days,
                    trace_error_retention_days=active.trace_error_retention_days,
                    ai_retention_days=active.ai_event_retention_days,
                    ai_critical_retention_days=active.ai_event_critical_retention_days,
                    audit_retention_days=active.audit_retention_days,
                )
                logger.info(
                    "保留清理完成 trace=%d ai=%d audit_expired=%d",
                    report.trace_deleted,
                    report.ai_deleted,
                    report.audit_expired,
                )
            except Exception:  # noqa: BLE001 - 清理失败不能拖垮服务
                logger.exception("保留清理失败")

    task = asyncio.create_task(recover())
    retention_task = asyncio.create_task(retention_loop()) if active.retention_enabled else None
    yield
    try:
        await asyncio.wait_for(task, timeout=30)
    except TimeoutError:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    finally:
        if retention_task is not None:
            retention_task.cancel()
            await asyncio.gather(retention_task, return_exceptions=True)
        await trace_sink.aclose()
        close = getattr(_app.state.oms, "close", None)
        if callable(close):
            close()
        await trace_engine.dispose()
        await engine.dispose()


def create_app(settings_override: Settings | None = None) -> FastAPI:
    configure_logging()
    active = settings_override or settings
    app = FastAPI(title="Customer Service Agent API", version="0.1.0", lifespan=lifespan)
    app.state.settings = active
    app.state.audit_writer = SqlAuditWriter(session_factory)

    @app.exception_handler(AuditWriteError)
    async def _audit_write_error(_request: Request, _error: AuditWriteError) -> JSONResponse:
        # 审计是强一致数据；写失败不能静默成功。Trace 写入失败不经过这里。
        return JSONResponse(status_code=503, content=error_envelope(ErrorCode.INTERNAL_ERROR))

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, error: ApiError) -> JSONResponse:
        # 401/403/429 是安全事件：独立事务审计，写失败不改写原始响应。
        await audit_api_error(request, error)
        return await api_error_handler(request, error)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, error: RequestValidationError) -> Response:
        # 新 M1 API 使用统一封套；内部调试接口保持 FastAPI 默认格式。
        if request.url.path.startswith(("/customer/", "/workspace/")):
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

    async def _attach_trace_sink(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        base = getattr(app.state, "trace_sink", None)
        if base is None:
            return await call_next(request)
        sink = SampledTraceSink(base, active.trace_sample_rate)
        with use_trace_sink(sink):
            return await call_next(request)

    # 后添加的中间件先执行：Trace 上下文最外层，其次请求关联标识，最后校验来源
    app.middleware("http")(verify_origin)
    app.middleware("http")(attach_request_id)
    app.middleware("http")(_attach_trace_sink)
    if active.m1_enabled:
        app.include_router(customer_router)
        app.include_router(employee_router)
        app.include_router(workspace_router)
    if active.test_accounts_enabled and isinstance(app.state.oms, MockOmsAdapter):
        app.include_router(admin_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics_view() -> PlainTextResponse:
        return PlainTextResponse(metrics.render())

    return app


app = create_app()
