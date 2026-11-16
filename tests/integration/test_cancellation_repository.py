"""真实 SQL 仓储：创建、读取、保存与归属隔离。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from services.api.auth import Identity
from services.api.db import session_factory
from services.api.domain.cancellation import CancellationState
from services.api.models import CancellationRequest as CancellationRow
from services.workflows.cancel import (
    CancellationTask,
    SqlCancellationRepository,
    TaskConflict,
    TaskNotFound,
)
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

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
    from services.mock_oms.service import MockOms
    from services.tools.cancel import build_cancel_gateway
    from services.workflows.cancel import CancellationWorkflow

    oms = MockOms()
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
        oms.submit_cancel("tenant-a", "user-a1", "ORD-10001", "idem-recover")
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
    from services.mock_oms.service import MockOms
    from services.tools.cancel import build_cancel_gateway
    from services.workflows.cancel import CancellationWorkflow

    oms = MockOms()
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
                state=CancellationState.SUBMIT_UNKNOWN,
                idempotency_key="idem-fail",
            )
        )
        await repo.commit()
        oms.submit_cancel("tenant-a", "user-a1", "ORD-10001", "idem-sub")

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
                state=CancellationState.SUBMIT_UNKNOWN,
                idempotency_key="idem-rec-2",
            )
        )
        await repo.create(
            task(
                id="task-rec-done",
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
        assert first.expires_at == datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
        assert first.reason_code == "SHIPPED"
        assert first.conversation_id == "conv-1"
        assert first.last_error_code == "DEPENDENCY_TIMEOUT"
        assert first.oms_request_id == "oms-1"
        assert first.version == 3

        await session.execute(delete(CancellationRow).where(CancellationRow.id.in_(ids)))
        await session.commit()
