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
