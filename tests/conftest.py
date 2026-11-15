"""测试夹具：每个用例前清空服务端会话，避免用例互相污染。"""

import pytest

from services.api import auth
from services.api.settings import settings


@pytest.fixture(autouse=True)
def _development_environment(monkeypatch) -> None:
    """测试默认按开发环境运行；生产门禁用例自行覆盖。"""
    monkeypatch.setattr(settings, "environment", "development")


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    auth._sessions.clear()
