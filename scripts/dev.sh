#!/usr/bin/env bash
# 本地一键启动：准备 .env、创建/迁移数据库、安装依赖，同时启动 API 与 Web。
# 用法：./scripts/dev.sh [--no-install]
set -euo pipefail
cd "$(dirname "$0")/.."

# 非交互环境（CI/agent）默认让 pnpm 走非交互安装；
# 否则 pnpm 在需要清理 node_modules 时会因无 TTY 拒绝执行。
if [ ! -t 0 ] && [ -z "${CI:-}" ]; then
  export CI=true
fi

NO_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --no-install) NO_INSTALL=1 ;;
    -h | --help)
      echo "用法：./scripts/dev.sh [--no-install]"
      echo "  --no-install  强制跳过依赖安装（调试用）"
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

DEPS_HASH_FILE=".dev-deps.sha"
deps_hash() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 pyproject.toml uv.lock apps/web/package.json apps/web/pnpm-lock.yaml \
      apps/chat/package.json apps/chat/pnpm-lock.yaml \
      apps/workspace/package.json apps/workspace/pnpm-lock.yaml \
      packages/contracts/package.json packages/contracts/pnpm-lock.yaml \
      | shasum -a 256 | awk '{print $1}'
  else
    sha256sum pyproject.toml uv.lock apps/web/package.json apps/web/pnpm-lock.yaml \
      apps/chat/package.json apps/chat/pnpm-lock.yaml \
      apps/workspace/package.json apps/workspace/pnpm-lock.yaml \
      packages/contracts/package.json packages/contracts/pnpm-lock.yaml \
      | sha256sum | awk '{print $1}'
  fi
}

if [ "$NO_INSTALL" = "1" ]; then
  echo "跳过依赖安装（--no-install）。"
elif [ -d .venv ] && [ -d apps/web/node_modules ] && [ -d apps/chat/node_modules ] \
  && [ -d apps/workspace/node_modules ] \
  && [ -d packages/contracts/node_modules ] && [ -f "$DEPS_HASH_FILE" ] \
  && [ "$(cat "$DEPS_HASH_FILE")" = "$(deps_hash)" ]; then
  echo "依赖未变化，跳过安装。"
else
  echo "安装/同步依赖..."
  uv sync --frozen
  pnpm -C apps/web install --frozen-lockfile
  pnpm -C apps/chat install --frozen-lockfile
  pnpm -C apps/workspace install --frozen-lockfile
  pnpm -C packages/contracts install --frozen-lockfile
  deps_hash >"$DEPS_HASH_FILE"
fi

uv run alembic upgrade head

if [ -z "${MODEL_API_KEY:-}" ]; then
  echo "提示：MODEL_API_KEY 为空，开发环境会用假模型；聊天只会返回未知意图，不适合演示。"
fi

BACKEND_PID=""
CHAT_PID=""
WORKSPACE_PID=""
kill_pid() {
  # 参数为空表示未启动，直接跳过
  [ -n "$1" ] || return 0
  kill "$1" 2>/dev/null || true
}
wait_pid() {
  [ -n "$1" ] || return 0
  wait "$1" 2>/dev/null || true
}
cleanup() {
  trap - EXIT INT TERM
  # 先全部发 TERM，再逐个回收，避免等一个进程时其他进程还在跑
  kill_pid "$BACKEND_PID"
  kill_pid "$CHAT_PID"
  kill_pid "$WORKSPACE_PID"
  wait_pid "$BACKEND_PID"
  wait_pid "$CHAT_PID"
  wait_pid "$WORKSPACE_PID"
}
trap cleanup EXIT INT TERM

echo "启动 API       http://127.0.0.1:8000"
echo "启动 Chat      http://localhost:3000"
echo "启动 Workspace http://localhost:3001  （Ctrl-C 同时停止）"
uv run uvicorn backend.api.main:app --reload --port 8000 &
BACKEND_PID=$!
pnpm -C apps/chat dev &
CHAT_PID=$!
PORT=3001 pnpm -C apps/workspace dev &
WORKSPACE_PID=$!

wait "$BACKEND_PID" "$CHAT_PID" "$WORKSPACE_PID"
