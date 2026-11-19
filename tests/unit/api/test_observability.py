"""Trace 脱敏、幂等键摘要与日志允许清单（AC-17、AC-18）。"""

import logging

from backend.platform.observability import (
    AuditWriteError,
    TraceWriteError,
    idempotency_digest,
    log_event,
    redact_event,
    redact_response,
)
from backend.tools.gateway import GatewayError


def test_审计元数据只保留允许字段_AC_18() -> None:
    event = {
        "trace_id": "t-1",
        "tenant_id": "tenant-a",
        "user_id": "user-a1",
        "order_id": "ORD-10001",
        "content": "我的手机号 13800138000",
        "token": "sk-secret",
        "card": "4111111111111111",
        "address": "某市某路 1 号",
        "idempotency_key": "raw-key",
        "idempotency_key_digest": "abc123",
    }
    assert redact_event(event) == {
        "trace_id": "t-1",
        "tenant_id": "tenant-a",
        "user_id": "user-a1",
        "order_id": "ORD-10001",
        "idempotency_key_digest": "abc123",
    }


def test_幂等键只输出十六位摘要_AC_18() -> None:
    digest = idempotency_digest("raw-idempotency-key")
    assert digest is not None
    assert len(digest) == 16
    assert digest != "raw-idempotency-key"
    assert digest == idempotency_digest("raw-idempotency-key")
    assert idempotency_digest(None) is None


def test_业务响应只保留状态字段_AC_17() -> None:
    response = {
        "order_id": "ORD-10001",
        "order_status": "PAID_UNFULFILLED",
        "cancelable": True,
        "amount_cents": 39900,
        "items": [{"name": "无线耳机"}],
        "payment": {"card": "4111111111111111"},
    }
    assert redact_response(response) == {
        "order_id": "ORD-10001",
        "order_status": "PAID_UNFULFILLED",
        "cancelable": True,
    }
    assert redact_response([response]) == [
        {"order_id": "ORD-10001", "order_status": "PAID_UNFULFILLED", "cancelable": True}
    ]


def test_结构化日志不含正文与敏感字段_AC_18(caplog) -> None:
    caplog.set_level(logging.INFO, logger="trace-test")
    logger = logging.getLogger("trace-test")
    log_event(
        logger,
        "message_handled",
        trace_id="t-1",
        tenant_id="tenant-a",
        user_id="user-a1",
        content="手机号 13800138000",
        token="sk-secret",  # noqa: S106 - 测试注入
    )
    assert "13800138000" not in caplog.text
    assert "sk-secret" not in caplog.text
    assert '"event": "message_handled"' in caplog.text
    assert '"trace_id": "t-1"' in caplog.text


def test_审计与trace异常都不是网关业务异常_AC_18() -> None:
    assert not issubclass(AuditWriteError, GatewayError)
    assert not issubclass(TraceWriteError, GatewayError)
    assert not issubclass(AuditWriteError, TraceWriteError)


async def test_审计写失败映射为503_AC_18() -> None:
    from backend.api.main import create_app

    handler = create_app().exception_handlers[AuditWriteError]
    response = await handler(None, AuditWriteError("audit down"))  # type: ignore[arg-type]

    assert response.status_code == 503
    assert b'"code":"INTERNAL_ERROR"' in response.body


def test_应用创建后配置日志handler_AC_18() -> None:
    from backend.api.main import configure_logging, create_app

    create_app()
    configure_logging()
    import sys

    assert any(
        isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout
        for handler in logging.getLogger().handlers
    )
    assert logging.getLogger().level <= logging.INFO
