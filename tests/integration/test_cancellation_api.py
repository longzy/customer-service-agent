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


class ConflictRepository(MemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.saves = 0

    async def save(self, task: CancellationTask) -> None:
        self.saves += 1
        if self.saves > 1:
            from services.workflows.cancel import TaskConflict

            raise TaskConflict(task.id)
        await super().save(task)


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


def test_越权与不存在订单返回404_AC_02() -> None:
    with make_client(MemoryRepository()) as api:
        login(api)
        for order_id in ("ORD-10005", "ORD-99999"):
            response = api.post("/cancellation-requests", json={"order_id": order_id})
            assert response.status_code == 404
            assert response.json()["code"] == "NOT_FOUND_OR_UNAUTHORIZED"


def test_响应不暴露幂等键_AC_09() -> None:
    with make_client(MemoryRepository()) as api:
        login(api)
        body = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()
        assert "idempotency_key" not in body
        assert "tenant_id" not in body


def test_主动放弃_AC_06() -> None:
    with make_client(MemoryRepository()) as api:
        login(api)
        task_id = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()["id"]
        body = api.post(f"/cancellation-requests/{task_id}/abandon").json()
        assert body["state"] == "ABANDONED"


def test_并发更新返回409_基座豁免() -> None:
    with make_client(ConflictRepository()) as api:
        login(api)
        task_id = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()["id"]
        assert api.post(f"/cancellation-requests/{task_id}/confirm").status_code == 409


def test_不接受客户端会话标识_AC_04() -> None:
    with make_client(MemoryRepository()) as api:
        login(api)
        response = api.post(
            "/cancellation-requests",
            json={"order_id": "ORD-10001", "conversation_id": "conv-9"},
        )
        assert response.status_code == 422


def test_查询时冲突返回409_基座豁免() -> None:
    from datetime import UTC, datetime

    from services.api.domain.cancellation import CancellationState
    from services.workflows.cancel import CancellationTask

    class ConflictOnSave(MemoryRepository):
        async def save(self, task: CancellationTask) -> None:
            from services.workflows.cancel import TaskConflict

            raise TaskConflict(task.id)

    repo = ConflictOnSave()
    repo.tasks["task-expired"] = CancellationTask(
        id="task-expired",
        tenant_id="tenant-a",
        user_id="user-a1",
        order_id="ORD-10001",
        state=CancellationState.AWAITING_CONFIRMATION,
        idempotency_key="idem-expired-key",
        expires_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    with make_client(repo) as api:
        login(api)
        assert api.get("/cancellation-requests/task-expired").status_code == 409


def test_资格拒绝返回原因与下一步_AC_16() -> None:
    with make_client(MemoryRepository()) as api:
        login(api)
        body = api.post("/cancellation-requests", json={"order_id": "ORD-10003"}).json()
        assert body["state"] == "ELIGIBILITY_REJECTED"
        assert body["reason_code"] == "SHIPPED"
        assert body["state_text"] == "不可取消，并说明原因"
        assert body["reason_text"] == "订单已发货"
        assert body["next_step"] == "如需进一步处理，可转人工。"


def test_等待确认返回下一步且无原因_AC_16() -> None:
    with make_client(MemoryRepository()) as api:
        login(api)
        body = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()
        assert body["state"] == "AWAITING_CONFIRMATION"
        assert body["reason_text"] is None
        assert body["next_step"] == "请在确认卡片中选择“确认取消”或“不取消”。"
