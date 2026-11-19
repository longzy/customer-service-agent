"""读写 session 分离：GET 不再提交空事务，last_seen_at 按会话节流刷新。"""

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from backend.api.main import create_app
from backend.identity import customer_sessions
from backend.platform.models import ServiceCustomerSession
from tests.integration.customer_support import (
    cleanup_customer_db,
    login_customer,
    prepare_customer_db,
)
from tests.integration.db_support import with_db
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def _last_seen() -> Any:
    async def read(db: Any) -> Any:
        row = (await db.execute(select(ServiceCustomerSession))).scalar_one()
        return row.last_seen_at

    return asyncio.run(with_db(read))


def _age_last_seen(minutes: int) -> None:
    async def age(db: Any) -> None:
        await db.execute(
            update(ServiceCustomerSession).values(
                last_seen_at=customer_sessions.utc_now() - timedelta(minutes=minutes)
            )
        )
        await db.commit()

    asyncio.run(with_db(age))


def test_GET_只按间隔刷新last_seen_基座豁免() -> None:
    app = create_app()
    with TestClient(app) as api:
        login_customer(api)
        assert _last_seen() is None

        # 第一次认证：无 last_seen，条件更新命中。
        assert api.get("/customer/session").status_code == 200
        first = _last_seen()
        assert first is not None

        # 3s 级轮询在 5 分钟窗口内不再写。
        assert api.get("/customer/messages").status_code == 200
        assert _last_seen() == first

        # 超过窗口后再次认证，条件更新重新命中。
        _age_last_seen(6)
        aged = _last_seen()
        assert api.get("/customer/messages").status_code == 200
        assert _last_seen() > aged
