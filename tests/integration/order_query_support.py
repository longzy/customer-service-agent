"""订单查询集成测试的公共装配（F-26 起共用）。

不改变 F-25 的 `test_order_query_AC_51.py`：新用例通过本模块构造应用与登录，
避免每个 AC 文件重复同一段客户会话装配。
"""

import asyncio
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update

from backend.agent_runtime.model import FakeModelClient
from backend.api.main import create_app
from backend.platform.models import ServiceCustomer
from tests.integration.customer_support import login_customer, with_db


def order_app(responses: dict[str, dict[str, Any]] | None = None) -> Any:
    """真实 API 装配 + 假模型；订单网关仍是进程内 Mock OMS。"""
    app = create_app()
    app.state.model_client = FakeModelClient(responses or {})
    return app


def api_client(app: Any) -> TestClient:
    return TestClient(app)


def login(api: TestClient, username: str = "customer_a") -> Any:
    return login_customer(api, username)


def send(api: TestClient, content: str, key: str | None = None) -> Any:
    return api.post(
        "/customer/messages",
        json={"content": content},
        headers={"Idempotency-Key": key or f"test-{uuid.uuid4()}"},
    )


def ai_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in body["messages"] if item["author_type"] == "ai"]


def bind_customer(username: str, oms_customer_id: str | None) -> None:
    """改写客户账号的 OMS 身份，用于空归属/无订单/跨客户隔离场景。"""

    async def write(db: Any) -> None:
        await db.execute(
            update(ServiceCustomer)
            .where(ServiceCustomer.username == username)
            .values(oms_customer_id=oms_customer_id)
        )
        await db.commit()

    asyncio.run(with_db(write))


def unbind_customer(username: str) -> None:
    """把客户账号与 OMS 身份解绑，用于验证空归属的安全降级。"""
    bind_customer(username, None)
