#!/bin/sh
# 在独立测试库上运行后端测试：建库（不存在时）→ 迁移 → pytest。
# 目的：集成测试不再直连开发库，也不因数据库不可用而静默跳过。
set -e
cd "$(git rev-parse --show-toplevel)"

export UV_CACHE_DIR=./.uv-cache
export ENVIRONMENT=test

DB_NAME="${TEST_DB_NAME:-customer_service_test}"
DB_HOST="${TEST_DB_HOST:-127.0.0.1}"
DB_PORT="${TEST_DB_PORT:-5432}"
DB_USER="${TEST_DB_USER:-$(whoami)}"
DB_PASSWORD="${TEST_DB_PASSWORD:-}"

if [ -n "$DB_PASSWORD" ]; then
  AUTH="${DB_USER}:${DB_PASSWORD}"
else
  AUTH="${DB_USER}"
fi

PSQL_URL="postgresql://${AUTH}@${DB_HOST}:${DB_PORT}"
APP_URL="postgresql+asyncpg://${AUTH}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

if ! psql "${PSQL_URL}/postgres" -tAc "select 1 from pg_database where datname='${DB_NAME}'" | grep -q 1; then
  echo "== 创建测试库 ${DB_NAME} =="
  createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
fi

echo "== 迁移测试库 =="
DATABASE_URL="$APP_URL" uv run alembic upgrade head

echo "== pytest（测试库 ${DB_NAME}）=="
DATABASE_URL="$APP_URL" uv run pytest "$@"
