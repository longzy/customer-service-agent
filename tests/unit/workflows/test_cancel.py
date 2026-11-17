"""Cancellation Workflow：资格、确认、恢复与惰性超时。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.adapters.oms.faults import FaultRule
from backend.adapters.oms.mock import MockOmsAdapter
from backend.adapters.oms.port import OmsAccess
from backend.domain.cancellation import CancellationState
from backend.errors import OrderNotFound
from backend.identity import Identity
from backend.tools.cancel import build_cancel_gateway
from backend.workflows.cancel import (
    CancellationRepository,
    CancellationTask,
    CancellationWorkflow,
    SqlCancellationRepository,
    TaskNotFound,
)

OWNER = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
OTHER = Identity("li-hua", "user-a2", "tenant-a", "李华", "示例商户 A")


def access() -> OmsAccess:
    return OmsAccess(tenant_id="tenant-a", user_id="user-a1")


class MemoryRepository:
    def __init__(self) -> None:
        self.tasks: dict[str, CancellationTask] = {}
        self.saves: list[CancellationState] = []
        self.created_states: list[CancellationState] = []
        self.commits = 0

    async def create(self, task: CancellationTask) -> None:
        self.created_states.append(task.state)
        self.tasks[task.id] = task

    async def get(self, task_id: str, identity: Identity) -> CancellationTask:
        task = self.tasks.get(task_id)
        if task is None or task.tenant_id != identity.tenant_id or task.user_id != identity.user_id:
            raise TaskNotFound(task_id)
        return task

    async def save(self, task: CancellationTask) -> None:
        self.saves.append(task.state)
        self.tasks[task.id] = task

    async def list_recoverable(self) -> list[CancellationTask]:
        return [
            task
            for task in self.tasks.values()
            if task.state in (CancellationState.SUBMITTING, CancellationState.SUBMIT_UNKNOWN)
        ]

    async def commit(self) -> None:
        self.commits += 1


def workflow(
    repo: CancellationRepository | None = None,
    oms: MockOmsAdapter | None = None,
    timeout: float = 2.0,
    now: Any = None,
    backoff: float = 0.01,
    audit: Any = None,
    confirmation: Any = None,
) -> tuple[CancellationWorkflow, MemoryRepository, MockOmsAdapter]:
    repository = repo or MemoryRepository()
    service = oms or MockOmsAdapter()
    flow = CancellationWorkflow(
        repository,
        build_cancel_gateway(service, timeout_seconds=timeout),
        retry_backoff_seconds=backoff,
        now=now,
        audit=audit,
        confirmation=confirmation,
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


async def test_重复确认返回同一结果_AC_09() -> None:
    flow, _, oms = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    first = await flow.confirm(OWNER, task.id, "t-1")
    second = await flow.confirm(OWNER, task.id, "t-1")
    assert first.state == second.state == CancellationState.ACCEPTED
    assert oms.get_cancel_result("tenant-a", task.idempotency_key) == "ACCEPTED"


async def test_响应丢失后恢复为受理_AC_10() -> None:
    oms = MockOmsAdapter()
    oms.faults.add(FaultRule(kind="lost_response", tool="submit_cancel"))
    flow, _, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.ACCEPTED


async def test_网关超时后恢复为受理_AC_10() -> None:
    oms = MockOmsAdapter()
    oms.faults.add(FaultRule(kind="delay", tool="submit_cancel", delay_ms=300))
    flow, _, _ = workflow(oms=oms, timeout=0.05, backoff=0.4)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.ACCEPTED


async def test_提交超时且查询持续失败进入人工_AC_12() -> None:
    oms = MockOmsAdapter()
    oms.faults.add(FaultRule(kind="delay", tool="submit_cancel", delay_ms=2000))
    oms.faults.add(FaultRule(kind="unavailable", tool="get_cancel_result", times=10))
    flow, _, _ = workflow(oms=oms, timeout=0.05)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.MANUAL_REVIEW


async def test_提交成功后读失败不降级_AC_05() -> None:
    oms = MockOmsAdapter()
    oms.faults.add(FaultRule(kind="unavailable", tool="get_cancel_result", times=5))
    flow, _, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    assert (await flow.confirm(OWNER, task.id, "t-1")).state == CancellationState.ACCEPTED


async def test_OMS返回未知时重试后人工_AC_12() -> None:
    oms = MockOmsAdapter()
    flow, repo, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    oms.submit_cancel(access(), "ORD-10001", task.idempotency_key)
    oms.set_cancel_result("tenant-a", task.idempotency_key, "UNKNOWN")
    stored = repo.tasks[task.id]
    stored.state = CancellationState.SUBMIT_UNKNOWN
    assert (await flow.get(OWNER, task.id, "t-1")).state == CancellationState.MANUAL_REVIEW


async def test_主动放弃不写OMS_AC_06() -> None:
    oms = MockOmsAdapter()
    flow, _, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    abandoned = await flow.abandon(OWNER, task.id)
    assert abandoned.state == CancellationState.ABANDONED
    with pytest.raises(OrderNotFound):
        oms.get_cancel_result("tenant-a", task.idempotency_key)


async def test_确认超时转为放弃_AC_19() -> None:
    clock = [datetime(2026, 11, 15, tzinfo=UTC)]
    oms = MockOmsAdapter()
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
    assert (await flow.get(OWNER, task.id, "t-1")).state == CancellationState.ABANDONED


async def test_他人任务不可见_AC_03() -> None:
    flow, _, _ = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    with pytest.raises(TaskNotFound):
        await flow.get(OTHER, task.id, "t-1")


async def test_默认有效期为三十分钟_AC_04() -> None:
    clock = [datetime(2026, 11, 15, tzinfo=UTC)]
    flow, _, _ = workflow(now=lambda: clock[0])
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    assert task.expires_at - clock[0] == timedelta(minutes=30)


async def test_查询可恢复状态会触发恢复_AC_10() -> None:
    oms = MockOmsAdapter()
    flow, repo, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    oms.submit_cancel(access(), "ORD-10001", task.idempotency_key)
    stored = repo.tasks[task.id]
    stored.state = CancellationState.SUBMIT_UNKNOWN
    assert (await flow.get(OWNER, task.id, "t-1")).state == CancellationState.ACCEPTED


async def test_放弃后重复放弃幂等_AC_06() -> None:
    flow, _, _ = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    await flow.abandon(OWNER, task.id)
    assert (await flow.abandon(OWNER, task.id)).state == CancellationState.ABANDONED


async def test_创建时先落收集态_AC_04() -> None:
    flow, repo, _ = workflow()
    await flow.request(OWNER, "ORD-10001", "t-1")
    assert repo.created_states == [CancellationState.COLLECTING]


async def test_不可取消任务重复确认返回原状态_AC_04() -> None:
    flow, _, _ = workflow()
    task = await flow.request(OWNER, "ORD-10003", "t-1")
    assert (
        await flow.confirm(OWNER, task.id, "t-1")
    ).state == CancellationState.ELIGIBILITY_REJECTED


async def test_提交被OMS拒绝_AC_07() -> None:
    oms = MockOmsAdapter()
    flow, _, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    oms.submit_cancel(access(), "ORD-10001", "another-key-123")
    confirmed = await flow.confirm(OWNER, task.id, "t-1")
    assert confirmed.state == CancellationState.REJECTED


async def test_提交中状态确认触发恢复_AC_10() -> None:
    oms = MockOmsAdapter()
    flow, repo, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    oms.submit_cancel(access(), "ORD-10001", task.idempotency_key)
    stored = repo.tasks[task.id]
    stored.state = CancellationState.SUBMITTING
    assert (await flow.confirm(OWNER, task.id, "t-1")).state == CancellationState.ACCEPTED


async def test_受理后可推进为已取消_AC_05() -> None:
    oms = MockOmsAdapter()
    flow, _, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    await flow.confirm(OWNER, task.id, "t-1")
    oms.set_cancel_result("tenant-a", task.idempotency_key, "CANCELLED")
    assert (await flow.get(OWNER, task.id, "t-1")).state == CancellationState.CANCELLED


async def test_受理后查询失败保持受理_AC_05() -> None:
    oms = MockOmsAdapter()
    flow, _, _ = workflow(oms=oms)
    task = await flow.request(OWNER, "ORD-10001", "t-1")
    await flow.confirm(OWNER, task.id, "t-1")
    oms.faults.add(FaultRule(kind="unavailable", tool="get_cancel_result", times=3))
    assert (await flow.get(OWNER, task.id, "t-1")).state == CancellationState.ACCEPTED


async def test_会话关联写入任务_AC_04() -> None:
    flow, repo, _ = workflow()
    task = await flow.request(OWNER, "ORD-10001", "t-1", conversation_id="conv-9")
    assert repo.tasks[task.id].conversation_id == "conv-9"


class _CapturingWorkflow(CancellationWorkflow):
    def __init__(self, repo: CancellationRepository) -> None:
        super().__init__(repo, None)  # type: ignore[arg-type]
        self.calls: list[tuple[Identity, CancellationTask, str]] = []

    async def _recover(
        self, identity: Identity, task: CancellationTask, trace_id: str
    ) -> CancellationTask:
        self.calls.append((identity, task, trace_id))
        if task.id == "task-conflict":
            from backend.workflows.cancel import TaskConflict

            raise TaskConflict(task.id)
        return task


async def test_启动恢复身份与跳过冲突_AC_12() -> None:
    repo = MemoryRepository()
    for task_id in ("task-ok", "task-conflict"):
        repo.tasks[task_id] = CancellationTask(
            id=task_id,
            tenant_id="tenant-a",
            user_id="user-a1",
            order_id="ORD-10001",
            state=CancellationState.SUBMIT_UNKNOWN,
            idempotency_key=f"idem-{task_id}",
            trace_id="trace-startup",
            expires_at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
        )
    flow = _CapturingWorkflow(repo)
    assert await flow.recover_pending("trace-startup") == 1
    assert [task.id for _, task, _ in flow.calls] == ["task-ok", "task-conflict"]
    identity, task, trace_id = flow.calls[0]
    assert identity.account_id == "startup-recovery"
    assert identity.tenant_id == "tenant-a"
    assert identity.user_id == "user-a1"
    assert identity.display_name == ""
    assert identity.tenant_name == ""
    assert task.id == "task-ok"
    assert trace_id == "trace-startup"


async def test_启动恢复空列表返回零_AC_12() -> None:
    flow = _CapturingWorkflow(MemoryRepository())
    assert await flow.recover_pending("trace-empty") == 0
    assert flow.calls == []


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> Any:
        return iter(self._rows)


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.statement: Any = None

    async def execute(self, statement: Any) -> _Result:
        self.statement = statement
        return _Result(self._rows)


async def test_可恢复查询字段映射与状态参数_AC_10() -> None:
    from backend.platform.models import CancellationRequest as CancellationRow

    row = CancellationRow(
        id="task-map",
        tenant_id="tenant-a",
        user_id="user-a1",
        order_id="ORD-10001",
        state="SUBMITTING",
        idempotency_key="idem-map",
        reason_code="SHIPPED",
        conversation_id="conv-1",
        last_error_code="DEPENDENCY_TIMEOUT",
        oms_request_id="oms-1",
        version=3,
        expires_at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
    )
    session = _Session([row])
    repo = SqlCancellationRepository(session)  # type: ignore[arg-type]
    items = await repo.list_recoverable()
    assert len(items) == 1
    item = items[0]
    assert item.id == "task-map"
    assert item.tenant_id == "tenant-a"
    assert item.user_id == "user-a1"
    assert item.order_id == "ORD-10001"
    assert item.state == CancellationState.SUBMITTING
    assert item.idempotency_key == "idem-map"
    assert item.expires_at == datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    assert item.reason_code == "SHIPPED"
    assert item.conversation_id == "conv-1"
    assert item.last_error_code == "DEPENDENCY_TIMEOUT"
    assert item.oms_request_id == "oms-1"
    assert item.version == 3
    params = session.statement.compile().params
    flattened: set[str] = set()
    for value in params.values():
        if isinstance(value, list):
            flattened.update(value)
        else:
            flattened.add(str(value))
    assert flattened == {"SUBMITTING", "SUBMIT_UNKNOWN"}


async def test_启动恢复使用任务trace_AC_17() -> None:
    repo = MemoryRepository()
    repo.tasks["task-trace"] = CancellationTask(
        id="task-trace",
        tenant_id="tenant-a",
        user_id="user-a1",
        order_id="ORD-10001",
        state=CancellationState.SUBMIT_UNKNOWN,
        idempotency_key="idem-trace",
        trace_id="trace-origin",
        expires_at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
    )
    flow = _CapturingWorkflow(repo)
    assert await flow.recover_pending("trace-ignored") == 1
    assert flow.calls[0][2] == "trace-origin"


async def test_请求与确认写状态转换审计_AC_17() -> None:
    events: list[dict[str, Any]] = []

    async def audit(event: dict[str, Any]) -> None:
        events.append(event)

    flow, _, _ = workflow(audit=audit)
    task = await flow.request(OWNER, "ORD-10001", "trace-audit")
    assert events[0] == {
        "trace_id": "trace-audit",
        "identity": OWNER,
        "task_id": task.id,
        "order_id": "ORD-10001",
        "from_state": "COLLECTING",
        "to_state": "AWAITING_CONFIRMATION",
        "reason_code": None,
        "result_status": "committed",
        "idempotency_key": task.idempotency_key,
    }
    await flow.confirm(OWNER, task.id)
    accepted = [event for event in events if event["to_state"] == "ACCEPTED"][0]
    assert accepted["identity"].account_id == "user-a1"
    assert any(event["to_state"] == "SUBMITTING" for event in events)
    assert any(event["to_state"] == "ACCEPTED" for event in events)
    assert all(event["trace_id"] == "trace-audit" for event in events)


async def test_放弃写状态转换审计_AC_17() -> None:
    events: list[dict[str, Any]] = []

    async def audit(event: dict[str, Any]) -> None:
        events.append(event)

    flow, _, _ = workflow(audit=audit)
    task = await flow.request(OWNER, "ORD-10001", "trace-abandon")
    await flow.abandon(OWNER, task.id)
    assert events[-1]["to_state"] == "ABANDONED"
    assert events[-1]["trace_id"] == "trace-abandon"


async def test_审计失败向上抛_AC_18() -> None:
    from backend.platform.observability import TraceSinkError

    async def failing(event: dict[str, Any]) -> None:
        raise TraceSinkError("down")

    flow, _, _ = workflow(audit=failing)
    with pytest.raises(TraceSinkError):
        await flow.request(OWNER, "ORD-10001", "trace-fail")


async def test_确认审计失败不被吞_AC_18() -> None:
    from backend.platform.observability import TraceSinkError

    events: list[dict[str, Any]] = []

    async def audit(event: dict[str, Any]) -> None:
        events.append(event)
        if event["to_state"] == "SUBMITTING":
            raise TraceSinkError("down")

    flow, _, _ = workflow(audit=audit)
    task = await flow.request(OWNER, "ORD-10001", "trace-confirm")
    with pytest.raises(TraceSinkError):
        await flow.confirm(OWNER, task.id)


async def test_确认写完整确认审计_AC_17() -> None:
    confirmations: list[dict[str, Any]] = []

    async def confirmation(event: dict[str, Any]) -> None:
        confirmations.append(event)

    flow, _, _ = workflow(confirmation=confirmation)
    task = await flow.request(OWNER, "ORD-10001", "trace-confirm-audit")
    await flow.confirm(OWNER, task.id)
    assert confirmations == [
        {
            "trace_id": "trace-confirm-audit",
            "identity": OWNER,
            "task_id": task.id,
            "order_id": "ORD-10001",
            "action": "confirm",
            "result_status": "committed",
            "idempotency_key": task.idempotency_key,
        }
    ]


async def test_放弃写完整确认审计_AC_17() -> None:
    confirmations: list[dict[str, Any]] = []

    async def confirmation(event: dict[str, Any]) -> None:
        confirmations.append(event)

    flow, _, _ = workflow(confirmation=confirmation)
    task = await flow.request(OWNER, "ORD-10001", "trace-abandon-audit")
    await flow.abandon(OWNER, task.id)
    assert confirmations[0]["action"] == "abandon"
    assert confirmations[0]["result_status"] == "abandoned"
    assert confirmations[0]["idempotency_key"] == task.idempotency_key
    await flow.abandon(OWNER, task.id)
    assert confirmations[-1]["result_status"] == "idempotent"


async def test_重复确认写幂等确认审计_AC_17() -> None:
    confirmations: list[dict[str, Any]] = []

    async def confirmation(event: dict[str, Any]) -> None:
        confirmations.append(event)

    flow, _, _ = workflow(confirmation=confirmation)
    task = await flow.request(OWNER, "ORD-10001", "trace-duplicate")
    await flow.confirm(OWNER, task.id)
    await flow.confirm(OWNER, task.id)
    assert [event["result_status"] for event in confirmations] == ["committed", "idempotent"]


async def test_确认审计失败不推进状态_AC_18() -> None:
    from backend.platform.observability import TraceSinkError

    async def failing(event: dict[str, Any]) -> None:
        raise TraceSinkError("down")

    flow, _, _ = workflow(confirmation=failing)
    task = await flow.request(OWNER, "ORD-10001", "trace-confirm-fail")
    with pytest.raises(TraceSinkError):
        await flow.confirm(OWNER, task.id)
    assert task.state == CancellationState.AWAITING_CONFIRMATION
