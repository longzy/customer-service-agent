"""测试夹具：每个用例前清空服务端会话，避免用例互相污染。"""

import pytest

from services.api import auth


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    auth._sessions.clear()
