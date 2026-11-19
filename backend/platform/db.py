"""数据库连接、连接池与会话依赖。"""

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from backend.platform.settings import TEST_ENVIRONMENTS, settings


class Base(DeclarativeBase):
    pass


def _pool_options(*, pool_size: int, max_overflow: int, pool_timeout: float) -> dict[str, Any]:
    """测试库用 NullPool；生产按配置建池。

    TestClient 每个 portal 有自己的事件循环，连接池跨 loop 复用会在
    teardown 打印 "Event loop is closed"，因此测试环境不建池。
    """
    if settings.environment in TEST_ENVIRONMENTS:
        return {"poolclass": NullPool, "pool_pre_ping": True}
    return {
        "pool_pre_ping": True,
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_timeout": pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
    }


engine = create_async_engine(
    settings.database_url,
    **_pool_options(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
    ),
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

# Trace 单独建池：工具执行记录是辅助数据，不能和业务请求抢连接。
# 池满时按 `trace_pool_timeout` 快速失败，而不是等业务池的 30s。
trace_engine = create_async_engine(
    settings.database_url,
    **_pool_options(
        pool_size=settings.trace_pool_size,
        max_overflow=settings.trace_max_overflow,
        pool_timeout=settings.trace_pool_timeout,
    ),
)
trace_session_factory = async_sessionmaker(trace_engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """请求级 Unit of Work：成功提交，异常回滚。

    业务模块只 `flush`，不提交；独立事务（限速、安全审计、Trace）必须
    用独立 session factory 新开 session，不能复用本 session。
    """

    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()
