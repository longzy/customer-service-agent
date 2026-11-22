"""F-31 取消任务集成测试的公共装配。

复用订单查询的客户登录与 App 装配；本模块只补取消路由的快捷调用与任务行读取，
避免每个 AC 文件重复同一段请求样板。
"""

from typing import Any

from fastapi.testclient import TestClient

from backend.agent_runtime.model import FakeModelClient
from backend.api.main import create_app
from backend.platform.models import CancellationRequest
from backend.platform.settings import Settings
from tests.integration.customer_support import rows_of
from tests.integration.order_query_support import order_app

CANCELLATIONS = "/customer/cancellations"
ORDERS = "/customer/orders"


def cancellation_app(**overrides: Any) -> Any:
    """按需覆盖配置（例如 0 分钟有效期）的真实 API 装配 + 假模型。"""
    app = create_app(Settings(environment="development", **overrides))
    app.state.model_client = FakeModelClient({})
    return app


def api_client(app: Any) -> TestClient:
    return TestClient(app)


def create_cancellation(api: TestClient, order_id: str = "ORD-10001") -> Any:
    return api.post(CANCELLATIONS, json={"order_id": order_id})


def confirm_cancellation(api: TestClient, task_id: str) -> Any:
    return api.post(f"{CANCELLATIONS}/{task_id}/confirm")


def decline_cancellation(api: TestClient, task_id: str) -> Any:
    return api.post(f"{CANCELLATIONS}/{task_id}/decline")


def read_cancellation(api: TestClient, task_id: str) -> Any:
    return api.get(f"{CANCELLATIONS}/{task_id}")


def task_rows() -> list[CancellationRequest]:
    return rows_of(CancellationRequest)


def default_order_app() -> Any:
    """F-31 默认配置（24 小时有效期）的 App。"""
    return order_app()
