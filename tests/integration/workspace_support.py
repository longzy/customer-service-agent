"""工作台集成测试共享夹具：员工种子、会话与数据库清理。"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, text, update

from backend.identity.passwords import hash_password
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceCustomer,
    ServiceCustomerSession,
    ServiceEmployee,
    ServiceEmployeeSession,
    ServiceHandoff,
    ServiceMessage,
    ServiceRateLimitBucket,
)
from backend.platform.settings import settings
from tests.integration.db_support import rows_of as rows_of
from tests.integration.db_support import with_db as with_db

DEMO_CREDENTIAL = "demo-login-value"
EMPLOYEES = (
    ("agent_1", "坐席 1"),
    ("agent_2", "坐席 2"),
)
NON_AGENT = ("supervisor_x", "主管甲", "supervisor")
CUSTOMERS = (
    ("customer_a", "客户甲", "user-a1"),
    ("customer_b", "客户乙", "user-b1"),
)


async def reset_workspace_state(db: Any) -> None:
    # 审计只追加：行级 DELETE 被触发器拒绝，测试清理用 TRUNCATE。
    await db.execute(text("TRUNCATE service_audit_events"))
    await db.execute(delete(ServiceMessage))
    await db.execute(delete(ServiceAiEvent))
    await db.execute(delete(ServiceHandoff))
    await db.execute(delete(ServiceCustomerSession))
    await db.execute(delete(ServiceEmployeeSession))
    await db.execute(delete(ServiceConversation))
    await db.execute(delete(ServiceCustomer))
    await db.execute(delete(ServiceEmployee))
    await db.execute(delete(ServiceRateLimitBucket))
    await db.commit()


async def seed_workspace(db: Any) -> None:
    for username, display_name, oms_customer_id in CUSTOMERS:
        db.add(
            ServiceCustomer(
                id=f"cust-{username}",
                tenant_id=settings.m1_tenant_id,
                username=username,
                password_hash=hash_password(DEMO_CREDENTIAL),
                display_name=display_name,
                oms_customer_id=oms_customer_id,
                active=True,
            )
        )
    for index in range(1, 5):
        db.add(
            ServiceCustomer(
                id=f"cust-extra-{index}",
                tenant_id=settings.m1_tenant_id,
                username=f"extra_{index}",
                password_hash=hash_password(DEMO_CREDENTIAL),
                display_name=f"测试客户{index}",
                active=True,
            )
        )
    for username, display_name in EMPLOYEES:
        db.add(
            ServiceEmployee(
                id=f"emp-{username}",
                tenant_id=settings.m1_tenant_id,
                username=username,
                password_hash=hash_password(DEMO_CREDENTIAL),
                role="agent",
                display_name=display_name,
                active=True,
            )
        )
    username, display_name, role = NON_AGENT
    db.add(
        ServiceEmployee(
            id=f"emp-{username}",
            tenant_id=settings.m1_tenant_id,
            username=username,
            password_hash=hash_password(DEMO_CREDENTIAL),
            role=role,
            display_name=display_name,
            active=True,
        )
    )
    await db.commit()


def prepare_workspace_db() -> None:
    asyncio.run(with_db(reset_workspace_state))
    asyncio.run(with_db(seed_workspace))


def cleanup_workspace_db() -> None:
    asyncio.run(with_db(reset_workspace_state))


def login_employee(api: TestClient, username: str = "agent_1") -> Any:
    response = api.post(
        "/workspace/sessions",
        json={"username": username, "password": DEMO_CREDENTIAL},
    )
    assert response.status_code == 200, response.text
    return response


def set_employee_role(username: str, role: str) -> None:
    async def change(db: Any) -> None:
        await db.execute(
            update(ServiceEmployee).where(ServiceEmployee.username == username).values(role=role)
        )
        await db.commit()

    asyncio.run(with_db(change))


def seed_conversation(
    conversation_id: str,
    *,
    customer_id: str = "cust-customer_a",
    status: str = "CLAIMED",
    assigned_employee_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    async def create(db: Any) -> None:
        db.add(
            ServiceConversation(
                id=conversation_id,
                tenant_id=tenant_id or settings.m1_tenant_id,
                customer_id=customer_id,
                status=status,
                assigned_employee_id=assigned_employee_id,
                journey_id=f"journey-{conversation_id}",
            )
        )
        await db.commit()

    asyncio.run(with_db(create))


def seed_customer(
    customer_id: str,
    username: str,
    *,
    tenant_id: str,
    display_name: str,
) -> None:
    """播种一个客户账号；用于跨租户等需要独立客户的队列用例。"""

    async def create(db: Any) -> None:
        db.add(
            ServiceCustomer(
                id=customer_id,
                tenant_id=tenant_id,
                username=username,
                password_hash=hash_password(DEMO_CREDENTIAL),
                display_name=display_name,
                active=True,
            )
        )
        await db.commit()

    asyncio.run(with_db(create))


def seed_queued_handoff(
    handoff_id: str,
    *,
    conversation_id: str,
    customer_id: str = "cust-customer_a",
    status: str = "QUEUED",
    conversation_status: str = "QUEUED",
    assigned_employee_id: str | None = None,
    reason: str = "CUSTOMER_REQUEST",
    created_at: datetime | None = None,
    order_count: int = 0,
    summary: str | None = None,
    context: dict[str, object] | None = None,
    earlier_messages: tuple[str, ...] = (),
    last_message: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """播种一张交接单与会话；可选最后一条客户消息与系统排队提示。

    消息 `created_at` 比交接单晚 1 秒，模拟 F-03 的“客户消息 → 交接单 → 排队提示”顺序。
    """
    moment = created_at or datetime.now(UTC)
    tenant = tenant_id or settings.m1_tenant_id
    journey_id = f"journey-{conversation_id}"

    async def create(db: Any) -> None:
        db.add(
            ServiceConversation(
                id=conversation_id,
                tenant_id=tenant,
                customer_id=customer_id,
                status=conversation_status,
                assigned_employee_id=assigned_employee_id,
                journey_id=journey_id,
                created_at=moment,
                updated_at=moment,
                last_activity_at=moment,
            )
        )
        db.add(
            ServiceHandoff(
                id=handoff_id,
                tenant_id=tenant,
                conversation_id=conversation_id,
                customer_id=customer_id,
                status=status,
                reason=reason,
                priority="normal",
                summary=summary or f"{customer_id} 的交接摘要",
                context=context if context is not None else {"order_count": order_count},
                pending_step="等待坐席接入",
                version=0,
                journey_id=journey_id,
                created_at=moment,
                updated_at=moment,
            )
        )
        await db.flush()
        contents = [*earlier_messages]
        if last_message is not None:
            contents.append(last_message)
        for offset, content in enumerate(contents):
            db.add(
                ServiceMessage(
                    conversation_id=conversation_id,
                    author_type="customer",
                    author_id=customer_id,
                    content=content,
                    idempotency_key=None,
                    trace_id=str(uuid4()),
                    created_at=moment + timedelta(milliseconds=offset),
                )
            )
            # 逐条 flush 固定 bigserial 顺序，避免批量插入时消息 id 次序不确定。
            await db.flush()
        db.add(
            ServiceMessage(
                conversation_id=conversation_id,
                author_type="system",
                author_id=None,
                content="排队中，请稍候",
                idempotency_key=None,
                trace_id=str(uuid4()),
                created_at=moment + timedelta(seconds=1),
            )
        )
        await db.commit()

    asyncio.run(with_db(create))
