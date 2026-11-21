"""F-25：订单访问基座与指定订单查询（AC-50/AC-51）。

只覆盖"正文恰好含一个订单号"的确定性路径；最近订单、多单澄清与失败分级
由 F-26/F-27 承接。
"""

import asyncio
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from backend.agent_runtime.model import FakeModelClient
from backend.api.main import create_app
from backend.conversations.order_queries import NOT_FOUND_REPLY
from backend.platform.models import ServiceAiEvent, ServiceCustomer, ServiceHandoff
from tests.integration.customer_support import (
    cleanup_customer_db,
    login_customer,
    prepare_customer_db,
    rows_of,
    with_db,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    yield
    cleanup_customer_db()


def order_app(responses: dict[str, dict[str, Any]] | None = None) -> Any:
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


def unbind_customer(username: str) -> None:
    async def write(db: Any) -> None:
        await db.execute(
            update(ServiceCustomer)
            .where(ServiceCustomer.username == username)
            .values(oms_customer_id=None)
        )
        await db.commit()

    asyncio.run(with_db(write))


def test_客户查本人订单返回摘要_AC_51() -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "查 ORD-10001")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["status"] == "AI_ACTIVE"
        [message] = ai_messages(body)
        assert "ORD-10001" in message["content"]
        assert "已支付未发货" in message["content"]
        assert "¥399.00" in message["content"]
        assert "2026-11-10 10:00" in message["content"]
        assert message["payload"]["orders"][0]["order_id"] == "ORD-10001"
        assert message["payload"]["orders"][0]["status_label"] == "已支付未发货"
        assert "items" not in message["payload"]["orders"][0]

        # 轮询同样带 payload，刷新不重新查 OMS
        polled = api.get("/customer/messages", params={"after_id": 0})
        assert polled.status_code == 200
        assert polled.json()["messages"][-1]["payload"]["orders"][0]["order_id"] == "ORD-10001"

    assert rows_of(ServiceHandoff) == []
    events = rows_of(ServiceAiEvent)
    assert [(event.event_type, event.name, event.status) for event in events] == [
        ("order_query", "get_order", "ok")
    ]
    assert app.state.oms.calls["get_order"] == 1


def test_客户查他人订单与不存在订单不可区分_AC_51() -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_b")
        other = send(api, "查 ORD-10001")
        missing = send(api, "查 ORD-99999")
        assert other.status_code == 200, other.text
        assert missing.status_code == 200, missing.text

        [other_ai] = ai_messages(other.json())
        [missing_ai] = ai_messages(missing.json())
        assert other_ai["content"] == NOT_FOUND_REPLY
        assert missing_ai["content"] == NOT_FOUND_REPLY
        assert other_ai["content"] == missing_ai["content"]
        assert other_ai["payload"]["orders"] == []
        assert missing_ai["payload"]["orders"] == []

    assert rows_of(ServiceHandoff) == []


def test_未绑定oms身份查无此单且不调用oms_AC_51() -> None:
    unbind_customer("customer_a")
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "查 ORD-10001")
        assert response.status_code == 200, response.text
        [message] = ai_messages(response.json())
        assert message["content"] == NOT_FOUND_REPLY
        assert message["payload"]["orders"] == []

    assert app.state.oms.calls["get_order"] == 0
    events = rows_of(ServiceAiEvent)
    assert [(event.event_type, event.status) for event in events] == [("order_query", "unbound")]


def test_普通消息不触发订单查询_AC_51() -> None:
    app = order_app(
        {
            "你好": {
                "intent": "UNKNOWN",
                "confidence": 0.95,
                "reply": "您好，请问有什么可以帮您？",
            }
        }
    )
    with api_client(app) as api:
        login(api, "customer_a")
        response = send(api, "你好")
        assert response.status_code == 200, response.text
        [message] = ai_messages(response.json())
        assert message["content"] == "您好，请问有什么可以帮您？"
        assert message["payload"] is None

    assert app.state.oms.calls["get_order"] == 0


def test_同幂等键重放不重复查询_AC_51() -> None:
    app = order_app()
    with api_client(app) as api:
        login(api, "customer_a")
        key = "replay-order-query"
        first = send(api, "查 ORD-10001", key)
        second = send(api, "查 ORD-10001", key)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["messages"] == second.json()["messages"]

    assert app.state.oms.calls["get_order"] == 1
    assert len(rows_of(ServiceAiEvent)) == 1
