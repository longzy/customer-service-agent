"""测试夹具：每个用例前清空服务端会话，避免用例互相污染。"""

import pytest

from services import identity as auth
from services.platform.settings import settings


@pytest.fixture(autouse=True)
def _development_environment(monkeypatch) -> None:
    """测试默认按开发环境运行；生产门禁用例自行覆盖。"""
    monkeypatch.setattr(settings, "environment", "development")


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    auth._sessions.clear()


@pytest.fixture(autouse=True)
async def _dispose_db_engine():
    """避免跨用例复用绑定到旧事件循环的连接池。"""
    yield
    from services.platform.db import engine

    await engine.dispose()
