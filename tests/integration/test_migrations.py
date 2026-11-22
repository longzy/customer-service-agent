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
    if "_test_" not in name and not name.startswith("customer_service_review"):
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
