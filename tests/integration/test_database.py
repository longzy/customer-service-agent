"""数据库连通性检查：本地未启动 PostgreSQL 时跳过，避免 CI 环境误报。"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.platform.settings import settings


@pytest.mark.asyncio
async def test_database_reachable() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("select 1"))
            assert result.scalar_one() == 1
    except (OperationalError, OSError):
        pytest.skip("本地数据库不可用，跳过集成检查")
    finally:
        await engine.dispose()
