"""真实 SQL 仓储：创建、读取、保存与归属隔离。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from backend.adapters.oms.port import OmsAccess
from backend.domain.cancellation import CancellationState
from backend.identity import Identity
from backend.platform.db import session_factory
from backend.platform.models import CancellationRequest as CancellationRow
from backend.workflows.cancel import (
    CancellationTask,
    SqlCancellationRepository,
    TaskConflict,
    TaskNotFound,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


def access() -> OmsAccess:
    return OmsAccess(tenant_id="tenant-a", user_id="user-a1")


OWNER = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
OTHER = Identity("wang-qiang", "user-b1", "tenant-b", "王强", "示例商户 B")


def task(**overrides) -> CancellationTask:
    base = CancellationTask(
        id="task-test-1",
        tenant_id=OWNER.tenant_id,
        user_id=OWNER.user_id,
        order_id="ORD-10001",
        state=CancellationState.AWAITING_CONFIRMATION,
        idempotency_key="idem-test-unique",
        expires_at=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


async def test_创建读取保存与隔离_AC_04() -> None:
    async with session_factory() as session:
        repo = SqlCancellationRepository(session)
        await repo.create(task())
        await repo.commit()

        loaded = await repo.get("task-test-1", OWNER)
        assert loaded.state == CancellationState.AWAITING_CONFIRMATION
        with pytest.raises(TaskNotFound):
            await repo.get("task-test-1", OTHER)

        loaded.state = CancellationState.ACCEPTED
        await repo.save(loaded)
        await repo.commit()
        assert (await repo.get("task-test-1", OWNER)).state == CancellationState.ACCEPTED

        await session.execute(delete(CancellationRow).where(CancellationRow.id == "task-test-1"))
        await session.commit()


async def test_真实乐观锁冲突_AC_09() -> None:
    async with session_factory() as first, session_factory() as second:
        repo_first = SqlCancellationRepository(first)
        repo_second = SqlCancellationRepository(second)
        await first.execute(delete(CancellationRow).where(CancellationRow.id == "task-version"))
        await first.commit()
        await repo_first.create(task(id="task-version", idempotency_key="idem-version"))
        await repo_first.commit()

        left = await repo_first.get("task-version", OWNER)
        right = await repo_second.get("task-version", OWNER)
        left.state = CancellationState.ACCEPTED
        await repo_first.save(left)
        await repo_first.commit()

        right.state = CancellationState.ABANDONED
        with pytest.raises(TaskConflict):
            await repo_second.save(right)

        await first.execute(delete(CancellationRow).where(CancellationRow.id == "task-version"))
        await first.commit()


async def test_启动恢复悬挂任务_AC_10() -> None:
    from backend.adapters.oms.mock import MockOmsAdapter
    from backend.tools.cancel import build_cancel_gateway
    from backend.workflows.cancel import CancellationWorkflow

    oms = MockOmsAdapter()
    async with session_factory() as session:
        repo = SqlCancellationRepository(session)
        await session.execute(delete(CancellationRow).where(CancellationRow.id == "task-recover"))
        await session.commit()
        await repo.create(
            task(
                id="task-recover",
                state=CancellationState.SUBMIT_UNKNOWN,
                idempotency_key="idem-recover",
            )
        )
        await repo.commit()
        oms.submit_cancel(access(), "ORD-10001", "idem-recover")
        submits = oms.calls["submit_cancel"]

        workflow = CancellationWorkflow(
            repo,
            build_cancel_gateway(oms),
            max_retries=1,
            retry_backoff_seconds=0.01,
        )
        assert await workflow.recover_pending("startup") == 1
        assert (await repo.get("task-recover", OWNER)).state == CancellationState.ACCEPTED
        assert oms.calls["submit_cancel"] == submits, "恢复不应重复提交"

        await session.execute(delete(CancellationRow).where(CancellationRow.id == "task-recover"))
        await session.commit()


async def test_启动恢复_SUBMITTING与失败转人工_AC_12() -> None:
    from backend.adapters.oms.mock import MockOmsAdapter
    from backend.tools.cancel import build_cancel_gateway
    from backend.workflows.cancel import CancellationWorkflow

    oms = MockOmsAdapter()
    async with session_factory() as session:
        repo = SqlCancellationRepository(session)
        await session.execute(
            delete(CancellationRow).where(CancellationRow.id.in_(["task-sub", "task-fail"]))
        )
        await session.commit()
        await repo.create(
            task(
                id="task-sub",
                state=CancellationState.SUBMITTING,
                idempotency_key="idem-sub",
            )
        )
        await repo.create(
            task(
                id="task-fail",
                order_id="ORD-10002",
                state=CancellationState.SUBMIT_UNKNOWN,
                idempotency_key="idem-fail",
            )
        )
        await repo.commit()
        oms.submit_cancel(access(), "ORD-10001", "idem-sub")

        workflow = CancellationWorkflow(
            repo,
            build_cancel_gateway(oms),
            max_retries=1,
            retry_backoff_seconds=0.01,
        )
        assert await workflow.recover_pending("startup") == 2
        assert (await repo.get("task-sub", OWNER)).state == CancellationState.ACCEPTED
        assert (await repo.get("task-fail", OWNER)).state == CancellationState.MANUAL_REVIEW

        await session.execute(
            delete(CancellationRow).where(CancellationRow.id.in_(["task-sub", "task-fail"]))
        )
        await session.commit()


async def test_终态任务不被扫描_AC_10() -> None:
    async with session_factory() as session:
        repo = SqlCancellationRepository(session)
        await session.execute(delete(CancellationRow).where(CancellationRow.id == "task-done"))
        await session.commit()
        await repo.create(
            task(
                id="task-done",
                state=CancellationState.ACCEPTED,
                idempotency_key="idem-done",
            )
        )
        await repo.commit()
        names = [item.id for item in await repo.list_recoverable()]
        assert "task-done" not in names
        await session.execute(delete(CancellationRow).where(CancellationRow.id == "task-done"))
        await session.commit()


async def test_可恢复查询只返回两种状态并映射字段_AC_10() -> None:
    async with session_factory() as session:
        repo = SqlCancellationRepository(session)
        ids = ["task-rec-1", "task-rec-2", "task-rec-done"]
        await session.execute(delete(CancellationRow).where(CancellationRow.id.in_(ids)))
        await session.commit()
        await repo.create(
            task(
                id="task-rec-1",
                state=CancellationState.SUBMITTING,
                idempotency_key="idem-rec-1",
                trace_id="trace-map",
                reason_code="SHIPPED",
                conversation_id="conv-1",
                last_error_code="DEPENDENCY_TIMEOUT",
                oms_request_id="oms-1",
                version=3,
            )
        )
        await repo.create(
            task(
                id="task-rec-2",
                order_id="ORD-10002",
                state=CancellationState.SUBMIT_UNKNOWN,
                idempotency_key="idem-rec-2",
            )
        )
        await repo.create(
            task(
                id="task-rec-done",
                order_id="ORD-10003",
                state=CancellationState.ACCEPTED,
                idempotency_key="idem-rec-done",
            )
        )
        await repo.commit()

        items = {item.id: item for item in await repo.list_recoverable()}
        assert set(items) == {"task-rec-1", "task-rec-2"}
        first = items["task-rec-1"]
        assert first.tenant_id == OWNER.tenant_id
        assert first.user_id == OWNER.user_id
        assert first.order_id == "ORD-10001"
        assert first.state == CancellationState.SUBMITTING
        assert first.idempotency_key == "idem-rec-1"
        assert first.trace_id == "trace-map"
        assert first.expires_at == datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        assert first.reason_code == "SHIPPED"
        assert first.conversation_id == "conv-1"
        assert first.last_error_code == "DEPENDENCY_TIMEOUT"
        assert first.oms_request_id == "oms-1"
        assert first.version == 3

        await session.execute(delete(CancellationRow).where(CancellationRow.id.in_(ids)))
        await session.commit()


async def test_仓储全字段往返_AC_04() -> None:
    async with session_factory() as session:
        repo = SqlCancellationRepository(session)
        task_id = "task-roundtrip"
        await session.execute(delete(CancellationRow).where(CancellationRow.id == task_id))
        await session.commit()
        created = task(
            id=task_id,
            state=CancellationState.SUBMITTING,
            idempotency_key="idem-roundtrip",
            trace_id="trace-roundtrip",
            reason_code="SHIPPED",
            conversation_id="conv-roundtrip",
            last_error_code="DEPENDENCY_TIMEOUT",
            oms_request_id="oms-roundtrip",
            version=4,
        )
        await repo.create(created)
        await repo.commit()

        loaded = await repo.get(task_id, OWNER)
        assert loaded.id == created.id
        assert loaded.tenant_id == created.tenant_id
        assert loaded.user_id == created.user_id
        assert loaded.order_id == created.order_id
        assert loaded.state == created.state
        assert loaded.idempotency_key == created.idempotency_key
        assert loaded.expires_at == created.expires_at
        assert loaded.reason_code == created.reason_code
        assert loaded.conversation_id == created.conversation_id
        assert loaded.trace_id == created.trace_id
        assert loaded.last_error_code == created.last_error_code
        assert loaded.oms_request_id == created.oms_request_id
        assert loaded.version == created.version

        listed = {item.id: item for item in await repo.list_recoverable()}
        item = listed[task_id]
        assert item.tenant_id == created.tenant_id
        assert item.user_id == created.user_id
        assert item.order_id == created.order_id
        assert item.state == created.state
        assert item.idempotency_key == created.idempotency_key
        assert item.expires_at == created.expires_at
        assert item.reason_code == created.reason_code
        assert item.conversation_id == created.conversation_id
        assert item.trace_id == "trace-roundtrip"
        assert item.last_error_code == created.last_error_code
        assert item.oms_request_id == created.oms_request_id
        assert item.version == created.version

        loaded.state = CancellationState.SUBMIT_UNKNOWN
        loaded.reason_code = "FULFILLING"
        loaded.last_error_code = "INVALID_RESPONSE"
        loaded.oms_request_id = "oms-roundtrip-2"
        await repo.save(loaded)
        await repo.commit()

        saved = await repo.get(task_id, OWNER)
        assert saved.state == CancellationState.SUBMIT_UNKNOWN
        assert saved.reason_code == "FULFILLING"
        assert saved.last_error_code == "INVALID_RESPONSE"
        assert saved.oms_request_id == "oms-roundtrip-2"
        assert saved.version == 5
        assert saved.trace_id == "trace-roundtrip"

        await session.execute(delete(CancellationRow).where(CancellationRow.id == task_id))
        await session.commit()
