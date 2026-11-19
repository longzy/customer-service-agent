#!/bin/sh
# 在独立测试库上运行后端测试：建库（不存在时）→ 迁移 → pytest。
# 默认每次运行使用一次性库名（含 PID 与时间），退出时删除；
# 并行评审/门禁因此不会互删数据。TEST_DB_NAME 可显式固定库名（调试用）。
# TEST_DB_KEEP=1 保留一次性库，便于失败后现场排查。
set -e
cd "$(git rev-parse --show-toplevel)"

export UV_CACHE_DIR=./.uv-cache
# 测试不读开发者 .env：本地与 CI 用同一份配置来源，避免“本地绿、CI 红”。
export ENVIRONMENT=test
export SETTINGS_ENV_FILE=/dev/null

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

# 默认一次性库：并行跑 verify/评审时互不影响；显式 TEST_DB_NAME 保持固定。
if [ -n "${TEST_DB_NAME:-}" ]; then
  DB_NAME="$TEST_DB_NAME"
  DROP_ON_EXIT=0
else
  DB_NAME="customer_service_test_$$_$(date +%s)"
  DROP_ON_EXIT=1
fi

cleanup() {
  if [ "$DROP_ON_EXIT" = "1" ] && [ "${TEST_DB_KEEP:-0}" != "1" ]; then
    dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --if-exists "$DB_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

APP_URL="postgresql+asyncpg://${AUTH}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

if ! psql "${PSQL_URL}/postgres" -tAc "select 1 from pg_database where datname='${DB_NAME}'" | grep -q 1; then
  echo "== 创建测试库 ${DB_NAME} =="
  createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
fi

echo "== 迁移测试库 =="
DATABASE_URL="$APP_URL" uv run alembic upgrade head

echo "== pytest（测试库 ${DB_NAME}）=="
DATABASE_URL="$APP_URL" uv run pytest "$@"
