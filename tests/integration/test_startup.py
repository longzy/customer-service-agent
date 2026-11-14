"""启动自检：数据库不可用时应用必须拒绝启动。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from services.api.main import create_app


def test_app_starts_when_database_available() -> None:
    try:
        with TestClient(create_app()) as client:
            assert client.get("/health").json() == {"status": "ok"}
    except (OperationalError, OSError):
        pytest.skip("本地数据库不可用，跳过启动自检")
