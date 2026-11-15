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

        workflow = CancellationWorkflow(
            repo,
            build_cancel_gateway(oms),
            max_retries=1,
            retry_backoff_seconds=0.01,
        )
        assert await workflow.recover_pending("startup") == 1
        assert (await repo.get("task-recover", OWNER)).state == CancellationState.ACCEPTED

        await session.execute(delete(CancellationRow).where(CancellationRow.id == "task-recover"))
        await session.commit()
