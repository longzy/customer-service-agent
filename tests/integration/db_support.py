"""集成测试共用：独立 engine 的数据库访问与按主键排序读取。"""

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.platform.settings import settings


async def with_db(action: Any) -> Any:
    """每次开独立 engine，避免 TestClient 与测试库操作跨事件循环复用连接池。"""
    engine = create_async_engine(settings.database_url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            return await action(db)
    finally:
        await engine.dispose()


def rows_of(model: Any) -> list[Any]:
    async def read(db: Any) -> list[Any]:
        # 按主键排序：DELETE/INSERT 后 seq scan 顺序不稳定，消息顺序断言会抖动
        return list((await db.execute(select(model).order_by(model.id))).scalars())

    return asyncio.run(with_db(read))
