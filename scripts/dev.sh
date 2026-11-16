#!/usr/bin/env bash
# 本地一键启动：准备 .env、创建/迁移数据库、安装依赖，同时启动 API 与 Web。
# 用法：./scripts/dev.sh [--no-install]
set -euo pipefail
cd "$(dirname "$0")/.."

NO_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --no-install) NO_INSTALL=1 ;;
    -h | --help)
      echo "用法：./scripts/dev.sh [--no-install]"
      echo "  --no-install  跳过 uv sync / pnpm install"
      exit 0
      ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建 .env（来自 .env.example）；需要自然语言演示请在 .env 填 MODEL_API_KEY。"
fi
set -a
# shellcheck disable=SC1091
. ./.env
set +a

DB_NAME="${DB_NAME:-customer_service}"
if ! command -v psql >/dev/null 2>&1; then
  echo "缺少 psql；请先启动 PostgreSQL 17 并确保 psql 在 PATH。" >&2
  exit 1
fi
if ! psql -d "$DB_NAME" -c "select 1" >/dev/null 2>&1; then
  createdb "$DB_NAME"
  echo "已创建数据库 $DB_NAME"
fi

if [ "$NO_INSTALL" = "0" ]; then
  uv sync --frozen
  pnpm -C apps/web install --frozen-lockfile
fi

uv run alembic upgrade head

if [ -z "${MODEL_API_KEY:-}" ]; then
  echo "提示：MODEL_API_KEY 为空，开发环境会用假模型；聊天只会返回未知意图，不适合演示。"
fi

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  trap - EXIT INT TERM
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  [ -n "$BACKEND_PID" ] && wait "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && wait "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "启动 API  http://127.0.0.1:8000"
echo "启动 Web  http://localhost:3000  （Ctrl-C 同时停止）"
uv run uvicorn services.api.main:app --reload --port 8000 &
BACKEND_PID=$!
pnpm -C apps/web dev &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
