"""Cancellation Workflow：资格、确认、恢复与惰性超时。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from services.api.auth import Identity
from services.api.domain.cancellation import CancellationState
from services.errors import OrderNotFound
from services.mock_oms.faults import FaultRule
from services.mock_oms.service import MockOms
from services.tools.cancel import build_cancel_gateway
from services.workflows.cancel import (
    CancellationRepository,
    CancellationTask,
    CancellationWorkflow,
    InvalidTransition,
    TaskNotFound,
)

OWNER = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
OTHER = Identity("li-hua", "user-a2", "tenant-a", "李华", "示例商户 A")


class MemoryRepository:
    def __init__(self) -> None:
        self.tasks: dict[str, CancellationTask] = {}
        self.commits = 0

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
        self.commits += 1


def workflow(
    repo: CancellationRepository | None = None,
    oms: MockOms | None = None,
    timeout: float = 2.0,
    now: Any = None,
) -> tuple[CancellationWorkflow, MemoryRepository, MockOms]:
    repository = repo or MemoryRepository()
    service = oms or MockOms()
    flow = CancellationWorkflow(
        repository, build_cancel_gateway(service, timeout_seconds=timeout), now=now
    )
    return flow, repository, service


async def test_可取消订单进入等待确认_AC_04() -> None:
    flow, _, _ = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    assert task.state == CancellationState.AWAITING_CONFIRMATION
    assert task.reason_code is None


async def test_已发货订单拒绝且不写_AC_07() -> None:
    flow, _, oms = workflow()
    task = await flow.request(OWNER, "ORD-10003", "t-1")
    assert task.state == CancellationState.ELIGIBILITY_REJECTED
    assert task.reason_code == "SHIPPED"
    with pytest.raises(OrderNotFound):
        oms.get_cancel_result("tenant-a", task.idempotency_key)


async def test_确认后受理_AC_05() -> None:
    flow, _, oms = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.ACCEPTED
    assert oms.get_cancel_result("tenant-a", task.idempotency_key) == "ACCEPTED"


async def test_重复确认被拒绝_AC_05() -> None:
    flow, _, _ = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    await flow.confirm(OWNER, task.id, "t-1")
    with pytest.raises(InvalidTransition):
        await flow.confirm(OWNER, task.id, "t-1")


async def test_响应丢失后恢复为受理_AC_10() -> None:
    oms = MockOms()
    oms.faults.add(FaultRule(kind="lost_response", tool="submit_cancel"))
    flow, _, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.ACCEPTED


async def test_网关超时进入未知_AC_12() -> None:
    oms = MockOms()
    oms.faults.add(FaultRule(kind="delay", tool="submit_cancel", delay_ms=300))
    flow, _, _ = workflow(oms=oms, timeout=0.05)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.SUBMIT_UNKNOWN


async def test_确认超时转为放弃_AC_19() -> None:
    clock = [datetime(2026, 11, 15, tzinfo=UTC)]
    oms = MockOms()
    flow, _, _ = workflow(oms=oms, now=lambda: clock[0])
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    clock[0] += timedelta(minutes=31)
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.ABANDONED
    with pytest.raises(OrderNotFound):
        oms.get_cancel_result("tenant-a", task.idempotency_key)


async def test_惰性查询也将过期任务转为放弃_AC_19() -> None:
    clock = [datetime(2026, 11, 15, tzinfo=UTC)]
    flow, _, _ = workflow(now=lambda: clock[0])
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    clock[0] += timedelta(minutes=31)
    assert (await flow.get(OWNER, task.id)).state == CancellationState.ABANDONED


async def test_他人任务不可见_AC_03() -> None:
    flow, _, _ = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    with pytest.raises(TaskNotFound):
        await flow.get(OTHER, task.id)
