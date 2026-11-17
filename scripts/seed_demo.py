#!/usr/bin/env python3
"""创建/重置 M1 演示账号：客户 customer_a/customer_b，坐席 agent_1/agent_2。

用法：在 `.env` 设置 `DEMO_PASSWORD` 后运行 `python scripts/seed_demo.py`。
密码不落仓库、不打印；脚本可重复执行（按 tenant_id + username 幂等）。
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# 允许 `python scripts/seed_demo.py` 直接运行，而不要求 `-m scripts.seed_demo`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from backend.identity.passwords import hash_password  # noqa: E402
from backend.platform.db import session_factory  # noqa: E402
from backend.platform.models import ServiceCustomer, ServiceEmployee  # noqa: E402
from backend.platform.settings import Settings  # noqa: E402

DEMO_CUSTOMERS: tuple[tuple[str, str], ...] = (
    ("customer_a", "客户甲"),
    ("customer_b", "客户乙"),
)
DEMO_EMPLOYEES: tuple[tuple[str, str], ...] = (
    ("agent_1", "坐席 1"),
    ("agent_2", "坐席 2"),
)


async def seed(active: Settings) -> list[str]:
    password = active.demo_password
    if not password.strip():
        raise SystemExit("DEMO_PASSWORD 为空：请在 .env 设置演示密码后重试")
    changed: list[str] = []
    async with session_factory() as db:
        for username, display_name in DEMO_CUSTOMERS:
            statement = select(ServiceCustomer).where(
                ServiceCustomer.tenant_id == active.m1_tenant_id,
                ServiceCustomer.username == username,
            )
            row = (await db.execute(statement)).scalar_one_or_none()
            if row is None:
                db.add(
                    ServiceCustomer(
                        id=str(uuid4()),
                        tenant_id=active.m1_tenant_id,
                        username=username,
                        password_hash=hash_password(password),
                        display_name=display_name,
                        active=True,
                    )
                )
                changed.append(f"{username}（新建）")
                continue
            row.password_hash = hash_password(password)
            row.display_name = display_name
            row.active = True
            changed.append(f"{username}（重置密码）")
        for username, display_name in DEMO_EMPLOYEES:
            statement = select(ServiceEmployee).where(
                ServiceEmployee.tenant_id == active.m1_tenant_id,
                ServiceEmployee.username == username,
            )
            row = (await db.execute(statement)).scalar_one_or_none()
            if row is None:
                db.add(
                    ServiceEmployee(
                        id=str(uuid4()),
                        tenant_id=active.m1_tenant_id,
                        username=username,
                        password_hash=hash_password(password),
                        role="agent",
                        display_name=display_name,
                        active=True,
                    )
                )
                changed.append(f"{username}（坐席，新建）")
                continue
            row.password_hash = hash_password(password)
            row.display_name = display_name
            row.role = "agent"
            row.active = True
            changed.append(f"{username}（坐席，重置密码）")
        await db.commit()
    return changed


def main() -> int:
    active = Settings()
    changed = asyncio.run(seed(active))
    print("演示账号已就绪：")
    for item in changed:
        print(f"  - {item}")
    print(f"租户：{active.m1_tenant_id}；密码来自 DEMO_PASSWORD，未显示。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
