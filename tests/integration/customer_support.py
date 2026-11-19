"""客户集成测试共享夹具：独立 engine、清理、种子与查询。"""

import asyncio
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, text

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
from tests.integration.db_support import rows_of as rows_of
from tests.integration.db_support import with_db as with_db

DEMO_CREDENTIAL = "demo-login-value"
CUSTOMERS = (("customer_a", "客户甲"), ("customer_b", "客户乙"))


async def reset_customer_state(db: Any) -> None:
    # 审计只追加：行级 DELETE 被触发器拒绝，测试清理用 TRUNCATE。
    await db.execute(text("TRUNCATE service_audit_events"))
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
