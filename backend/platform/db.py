"""数据库连接与会话依赖。"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from backend.platform.settings import TEST_ENVIRONMENTS, settings


class Base(DeclarativeBase):
    pass


# 测试库用 NullPool：TestClient 每个 portal 有自己的事件循环，
# 连接池跨 loop 复用会在 teardown 打印 "Event loop is closed"。
_pool = NullPool if settings.environment in TEST_ENVIRONMENTS else None
engine = create_async_engine(settings.database_url, pool_pre_ping=True, poolclass=_pool)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
