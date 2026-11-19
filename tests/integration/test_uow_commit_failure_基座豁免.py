"""commit 失败时，响应必须在发送前变成 500，业务数据回滚。

用依赖 override 注入一个真实 session，但把 commit 替换为抛错；路由声明的
`scope="function"` 保留，因此异常发生在响应发送前。
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.api.main import create_app
from backend.platform.db import get_session, session_factory
from backend.platform.models import ServiceMessage
from tests.integration.customer_support import (
    cleanup_customer_db,
    login_customer,
    prepare_customer_db,
    rows_of,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


async def failing_uow():
    async with session_factory() as session:

        async def fail_commit() -> None:
            raise SQLAlchemyError("commit boom")

        session.commit = fail_commit  # type: ignore[method-assign]
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def test_commit失败返回500且消息未落库_基座豁免() -> None:
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as api:
        login_customer(api)
        app.dependency_overrides[get_session] = failing_uow
        response = api.post(
            "/customer/messages",
            json={"content": "你好"},
            headers={"Idempotency-Key": f"test-{uuid.uuid4()}"},
        )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert rows_of(ServiceMessage) == []
