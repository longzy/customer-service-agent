"""HTTP 适配层共享工具：可信客户端 IP、UTC 文本、配置与请求标识。"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Request

from backend.platform.settings import Settings


def client_ip(request: Request) -> str:
    """只信任直连 peer；不解析裸 X-Forwarded-For。"""
    return request.client.host if request.client is not None else "unknown"


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def settings_of(request: Request) -> Settings:
    active: Settings = request.app.state.settings
    return active


def trace_of(request: Request) -> str:
    """请求关联标识；中间件缺省时生成一次性标识，避免审计写入失败。"""
    return getattr(request.state, "trace_id", None) or str(uuid4())
