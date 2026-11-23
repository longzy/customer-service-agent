"""迁移 0013 升级/回滚回归（F-25 订单访问基座，AC-51）。"""

import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from backend.platform.settings import settings
from tests.integration.db_support import with_db
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

PREVIOUS_REVISION = "0012_trace_ai_fields"
NEW_COLUMNS = {
    ("service_customers", "oms_customer_id"),
    ("service_messages", "payload"),
}


def _require_test_database() -> None:
    """只允许在测试库跑 DDL，避免裸跑 pytest 时把开发库的列删掉。"""
    name = settings.database_url.rsplit("/", 1)[-1].split("?")[0]
    # 评审/安全评审用固定库；CI 的 verify/mutation 用 customer_service_test。
    allowed_prefixes = (
        "customer_service_review",
        "customer_service_security",
        "customer_service_test",
    )
    if "_test_" not in name and not name.startswith(allowed_prefixes):
        pytest.skip(f"迁移测试只允许在测试库运行，当前库：{name}")


def _config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.database_url)
    # migrations/env.py 只在 config_file_name 非空时调用 fileConfig；
    # 其默认 disable_existing_loggers=True 会禁掉同进程已导入的 logger，
    # 污染后续 caplog 用例（例如 backend.tools.gateway）。测试里跳过日志重配。
    config.config_file_name = None
    return config


def _columns() -> dict[tuple[str, str], tuple[str, str]]:
    """(表, 列) → (data_type, is_nullable)。"""

    async def read(db: object) -> dict[tuple[str, str], tuple[str, str]]:
        rows = (
            await db.execute(  # type: ignore[attr-defined]
                text(
                    "select table_name, column_name, data_type, is_nullable "
                    "from information_schema.columns "
                    "where table_name in ('service_customers','service_messages') "
                    "and column_name in ('oms_customer_id','payload')"
                )
            )
        ).all()
        return {(str(row[0]), str(row[1])): (str(row[2]), str(row[3])) for row in rows}

    return asyncio.run(with_db(read))


def _index_def() -> str | None:
    async def read(db: object) -> str | None:
        row = (
            await db.execute(  # type: ignore[attr-defined]
                text(
                    "select indexdef from pg_indexes where tablename='service_customers' "
                    "and indexname='uq_service_customers_tenant_oms'"
                )
            )
        ).first()
        return None if row is None else str(row[0])

    return asyncio.run(with_db(read))


def test_0013_升级回滚再升级_AC_51() -> None:
    _require_test_database()
    config = _config()
    try:
        command.downgrade(config, PREVIOUS_REVISION)
        assert _columns() == {}
        assert _index_def() is None
    finally:
        command.upgrade(config, "head")
    assert set(_columns()) == NEW_COLUMNS
    assert _columns()[("service_customers", "oms_customer_id")] == (
        "character varying",
        "YES",
    )
    assert _columns()[("service_messages", "payload")] == ("json", "YES")
    index_def = _index_def()
    assert index_def is not None
    assert "UNIQUE" in index_def
    assert "(tenant_id, oms_customer_id)" in index_def
    assert "WHERE (oms_customer_id IS NOT NULL)" in index_def


CANCELLATION_PREVIOUS_REVISION = "0013_order_query"
CANCELLATION_COLUMNS = {
    "requested_by_type",
    "requested_by_id",
    "confirmed_at",
    "confirmation_source",
    "confirmed_by_id",
}


def _cancellation_columns() -> set[str]:
    async def read(db: object) -> set[str]:
        rows = (
            await db.execute(  # type: ignore[attr-defined]
                text(
                    "select column_name from information_schema.columns "
                    "where table_name = 'cancellation_requests'"
                )
            )
        ).all()
        return {str(row[0]) for row in rows}

    return asyncio.run(with_db(read))


def _active_index_def() -> str | None:
    async def read(db: object) -> str | None:
        row = (
            await db.execute(  # type: ignore[attr-defined]
                text(
                    "select indexdef from pg_indexes where tablename='cancellation_requests' "
                    "and indexname='uq_cancellation_active_order'"
                )
            )
        ).first()
        return None if row is None else str(row[0])

    return asyncio.run(with_db(read))


def test_0014_取消列与活跃唯一索引可回滚_AC_60() -> None:
    """0014 只加法：新增发起/确认列与同订单活跃任务部分唯一索引，可回滚。"""
    _require_test_database()
    config = _config()
    try:
        command.downgrade(config, CANCELLATION_PREVIOUS_REVISION)
        assert CANCELLATION_COLUMNS.isdisjoint(_cancellation_columns())
        assert _active_index_def() is None
    finally:
        command.upgrade(config, "head")
    assert _cancellation_columns() >= CANCELLATION_COLUMNS
    index_def = _active_index_def()
    assert index_def is not None
    assert "UNIQUE" in index_def
    assert "(tenant_id, order_id)" in index_def
    assert "'AWAITING_CONFIRMATION'" in index_def
    assert "'ACCEPTED'" in index_def


def test_0014_回填发起人与重复活跃任务收尾_AC_60() -> None:
    """0014 升级前旧任务按客户发起回填；同订单重复活跃任务只保留最新。"""
    _require_test_database()
    config = _config()
    order_id = "ORD-MIG-0014"

    async def seed(db: object) -> None:
        from datetime import UTC, datetime

        await db.execute(  # type: ignore[attr-defined]
            text("delete from cancellation_requests where order_id = :order_id"),
            {"order_id": order_id},
        )
        for task_id, created_at, state in (
            ("task-mig-accepted", datetime(2026, 10, 31, tzinfo=UTC), "ACCEPTED"),
            ("task-mig-old", datetime(2026, 11, 1, tzinfo=UTC), "AWAITING_CONFIRMATION"),
            ("task-mig-new", datetime(2026, 11, 2, tzinfo=UTC), "AWAITING_CONFIRMATION"),
        ):
            await db.execute(  # type: ignore[attr-defined]
                text(
                    "insert into cancellation_requests "
                    "(id, tenant_id, user_id, order_id, state, idempotency_key, trace_id, "
                    " expires_at, created_at, updated_at, version) values "
                    "(:id, 'tenant-a', 'user-a1', :order_id, :state, "
                    " :idempotency_key, 'trace-mig', :expires, :created, :created, 0)"
                ),
                {
                    "id": task_id,
                    "order_id": order_id,
                    "idempotency_key": f"idem-{task_id}",
                    "state": state,
                    "expires": datetime(2026, 12, 1, tzinfo=UTC),
                    "created": created_at,
                },
            )
        await db.commit()  # type: ignore[attr-defined]

    async def read(db: object) -> dict[str, tuple[str, str | None, str | None]]:
        rows = (
            await db.execute(  # type: ignore[attr-defined]
                text(
                    "select id, state, requested_by_type, requested_by_id "
                    "from cancellation_requests where order_id = :order_id"
                ),
                {"order_id": order_id},
            )
        ).all()
        return {str(row[0]): (str(row[1]), row[2], row[3]) for row in rows}

    def cleanup() -> None:
        async def run(db: object) -> None:
            await db.execute(  # type: ignore[attr-defined]
                text("delete from cancellation_requests where order_id = :order_id"),
                {"order_id": order_id},
            )
            await db.commit()  # type: ignore[attr-defined]

        asyncio.run(with_db(run))

    try:
        command.downgrade(config, CANCELLATION_PREVIOUS_REVISION)
        asyncio.run(with_db(seed))
        command.upgrade(config, "head")

        rows = asyncio.run(with_db(read))
        assert rows["task-mig-accepted"][0] == "ACCEPTED"
        assert rows["task-mig-old"][0] == "ABANDONED"
        assert rows["task-mig-new"][0] == "ABANDONED"
        assert rows["task-mig-accepted"][1:] == ("CUSTOMER", "user-a1")
        assert rows["task-mig-old"][1:] == ("CUSTOMER", "user-a1")

        async def duplicate(db: object) -> None:
            from datetime import UTC, datetime

            await db.execute(  # type: ignore[attr-defined]
                text(
                    "insert into cancellation_requests "
                    "(id, tenant_id, user_id, order_id, state, idempotency_key, "
                    " expires_at, created_at, updated_at, version) values "
                    "('task-mig-dup', 'tenant-a', 'user-a1', :order_id, "
                    " 'AWAITING_CONFIRMATION', 'idem-task-mig-dup', :expires, "
                    " :created, :created, 0)"
                ),
                {
                    "order_id": order_id,
                    "expires": datetime(2026, 12, 1, tzinfo=UTC),
                    "created": datetime(2026, 11, 3, tzinfo=UTC),
                },
            )
            await db.commit()  # type: ignore[attr-defined]

        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            asyncio.run(with_db(duplicate))
    finally:
        cleanup()
        command.upgrade(config, "head")
