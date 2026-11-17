#!/usr/bin/env python3
"""重建本地开发库：停服务 → 清空 public schema → 迁移 → 重播种演示账号。

开发库是可抛弃资源；脚本只允许 development/test，且 DATABASE_URL 指向本机、
库名以 customer_service 开头。非交互运行必须显式传 `--yes`。

用法：
    uv run python scripts/reset_dev_db.py [--yes] [--keep-servers]
"""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.platform.settings import Settings  # noqa: E402

ALLOWED_ENVIRONMENTS = {"development", "test"}
LOCAL_HOSTS = {"", "127.0.0.1", "localhost", "::1"}


def _database_target(active: Settings) -> tuple[str, str]:
    parsed = urlparse(active.database_url.replace("+asyncpg", ""))
    return parsed.hostname or "", parsed.path.lstrip("/")


def _guard(active: Settings) -> tuple[str, str]:
    if active.environment not in ALLOWED_ENVIRONMENTS:
        raise SystemExit(
            f"拒绝执行：ENVIRONMENT={active.environment}，只允许 {sorted(ALLOWED_ENVIRONMENTS)}。"
        )
    host, database = _database_target(active)
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"拒绝执行：DATABASE_URL 指向非本机主机 {host}。")
    if not database.startswith("customer_service"):
        raise SystemExit(f"拒绝执行：数据库名 {database} 不是 customer_service*。")
    return host, database


def _confirm(database: str, yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("非交互模式需要 --yes；未执行任何操作。")
    print(f"将清空数据库 {database}，重新迁移并播种演示账号。")
    answer = input(f"确认请输入库名 {database}：").strip()
    if answer != database:
        raise SystemExit("确认不匹配，已取消。")


def _stop_servers() -> None:
    subprocess.run(  # noqa: S603 - 固定本地脚本路径
        [str(ROOT / "scripts" / "dev-stop.sh")], cwd=ROOT, check=False
    )


async def _reset_schema(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname = current_database() and pid <> pg_backend_pid()"
                )
            )
            await connection.execute(text("drop schema public cascade"))
            await connection.execute(text("create schema public"))
    finally:
        await engine.dispose()


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)  # noqa: S603 - 命令由本模块常量提供


def main() -> int:
    parser = argparse.ArgumentParser(description="重建本地开发库")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认")
    parser.add_argument("--keep-servers", action="store_true", help="不停止 3000/3001/8000")
    args = parser.parse_args()
    os.environ.setdefault("UV_CACHE_DIR", str(ROOT / ".uv-cache"))

    active = Settings()
    host, database = _guard(active)
    print(
        f"目标：{host or '本机 socket'}/{database}（environment={active.environment}）", flush=True
    )
    _confirm(database, args.yes)

    if not args.keep_servers:
        _stop_servers()
    asyncio.run(_reset_schema(active.database_url))
    _run(["uv", "run", "alembic", "upgrade", "head"])
    _run(["uv", "run", "python", "scripts/seed_demo.py"])
    print("开发库已重建并重新播种；运行 `make dev` 重新启动服务。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
