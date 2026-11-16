"""OMS Adapter factory：按配置选择 Mock 或 Http，生产缺配置即失败。"""

from urllib.parse import urlparse

import httpx

from services.adapters.oms.http import HttpOmsAdapter
from services.adapters.oms.mock import MockOmsAdapter
from services.adapters.oms.port import OmsPort
from services.platform.settings import TEST_ENVIRONMENTS, Settings


class OmsConfigError(RuntimeError):
    """启动期 OMS 配置错误；不进入 API 错误封套。"""


def _validated_url(raw: str) -> str:
    if any(char.isspace() for char in raw):
        raise OmsConfigError("OMS_BASE_URL 不能包含空白")
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError as error:
        raise OmsConfigError(f"OMS_BASE_URL 非法：{error}") from error
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise OmsConfigError("OMS_BASE_URL 必须是 http/https 且包含 host")
    if port is not None and not 1 <= port <= 65535:
        raise OmsConfigError("OMS_BASE_URL 端口必须在 1–65535")
    return raw


def build_oms(settings: Settings) -> OmsPort:
    raw = settings.oms_base_url.strip()
    if raw:
        url = _validated_url(raw)
        try:
            return HttpOmsAdapter(url, timeout=settings.oms_timeout_seconds)
        except (ValueError, httpx.InvalidURL) as error:
            raise OmsConfigError(f"OMS_BASE_URL 非法：{error}") from error
    if settings.environment in TEST_ENVIRONMENTS:
        return MockOmsAdapter()
    raise OmsConfigError(f"environment={settings.environment} 必须配置 OMS_BASE_URL，不能回落 Mock")
