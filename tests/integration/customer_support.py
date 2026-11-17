"""客户集成测试共享夹具：独立 engine、清理、种子与查询。"""

import asyncio
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.identity.passwords import hash_password
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceCustomer,
    ServiceCustomerSession,
    ServiceHandoff,
    ServiceMessage,
    ServiceRateLimitBucket,
)
from backend.platform.settings import settings

DEMO_CREDENTIAL = "demo-login-value"
CUSTOMERS = (("customer_a", "客户甲"), ("customer_b", "客户乙"))


async def with_db(action: Any) -> Any:
    """每次开独立 engine，避免 TestClient 与测试库操作跨事件循环复用连接池。"""
    engine = create_async_engine(settings.database_url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as db:
            return await action(db)
    finally:
        await engine.dispose()


async def reset_customer_state(db: Any) -> None:
    await db.execute(delete(ServiceMessage))
    await db.execute(delete(ServiceAiEvent))
    await db.execute(delete(ServiceHandoff))
    await db.execute(delete(ServiceCustomerSession))
    await db.execute(delete(ServiceConversation))
    await db.execute(delete(ServiceCustomer))
    await db.execute(delete(ServiceRateLimitBucket))
    await db.commit()


async def seed_customers(db: Any) -> None:
    for username, display_name in CUSTOMERS:
        db.add(
            ServiceCustomer(
                id=f"cust-{username}",
                tenant_id=settings.m1_tenant_id,
                username=username,
                password_hash=hash_password(DEMO_CREDENTIAL),
                display_name=display_name,
                active=True,
            )
        )
    await db.commit()


def prepare_customer_db() -> None:
    asyncio.run(with_db(reset_customer_state))
    asyncio.run(with_db(seed_customers))


def cleanup_customer_db() -> None:
    asyncio.run(with_db(reset_customer_state))


def login_customer(api: TestClient, username: str = "customer_a") -> Any:
    response = api.post(
        "/customer/sessions",
        json={"username": username, "password": DEMO_CREDENTIAL},
    )
    assert response.status_code == 200, response.text
    return response


def rows_of(model: Any) -> list[Any]:
    async def read(db: Any) -> list[Any]:
        # 按主键排序：DELETE/INSERT 后 seq scan 顺序不稳定，消息顺序断言会抖动
        return list((await db.execute(select(model).order_by(model.id))).scalars())

    return asyncio.run(with_db(read))
