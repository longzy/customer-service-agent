"""取消任务 API：资格、确认与归属（AC-04、AC-05、AC-07、AC-09）。"""

import pytest
from fastapi.testclient import TestClient

from services.api.auth import Identity
from services.api.cancellation_routes import get_repository
from services.api.main import create_app
from services.workflows.cancel import (
    CancellationRepository,
    CancellationTask,
    TaskNotFound,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


class MemoryRepository:
    def __init__(self) -> None:
        self.tasks: dict[str, CancellationTask] = {}

    async def create(self, task: CancellationTask) -> None:
        self.tasks[task.id] = task

    async def get(self, task_id: str, identity: Identity) -> CancellationTask:
        task = self.tasks.get(task_id)
        if task is None or task.tenant_id != identity.tenant_id or task.user_id != identity.user_id:
            raise TaskNotFound(task_id)
        return task

    async def save(self, task: CancellationTask) -> None:
        self.tasks[task.id] = task

    async def commit(self) -> None:
        return None


def make_client(repo: CancellationRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def login(api: TestClient, account: str = "zhang-ming") -> None:
    assert api.post("/session", json={"account_id": account}).status_code == 200


def test_可取消订单创建任务并确认_AC_04_AC_05() -> None:
    repo = MemoryRepository()
    with make_client(repo) as api:
        login(api)
        created = api.post("/cancellation-requests", json={"order_id": "ORD-10001"})
        assert created.status_code == 200
        body = created.json()
        assert body["state"] == "AWAITING_CONFIRMATION"
        confirmed = api.post(f"/cancellation-requests/{body['id']}/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["state"] == "ACCEPTED"


def test_已发货订单返回原因码_AC_07() -> None:
    repo = MemoryRepository()
    with make_client(repo) as api:
        login(api)
        body = api.post("/cancellation-requests", json={"order_id": "ORD-10003"}).json()
        assert body["state"] == "ELIGIBILITY_REJECTED"
        assert body["reason_code"] == "SHIPPED"


def test_他人任务不可见_AC_03() -> None:
    repo = MemoryRepository()
    with make_client(repo) as api:
        login(api)
        task_id = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()["id"]
        login(api, "li-hua")
        assert api.get(f"/cancellation-requests/{task_id}").status_code == 404
        assert api.post(f"/cancellation-requests/{task_id}/confirm").status_code == 404


def test_未认证被拒绝_AC_20() -> None:
    with make_client(MemoryRepository()) as api:
        assert api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).status_code == 401
