#!/bin/sh
# 本地开发状态：端口、数据库、迁移、模型模式与 OpenAPI 类型。
set -e
cd "$(git rev-parse --show-toplevel)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

echo "== 端口 =="
for port in 3000 8000; do
  if lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  $port: 监听中（$(lsof -tiTCP:"$port" -sTCP:LISTEN | tr '\n' ' ')）"
  else
    echo "  $port: 空闲"
  fi
done

echo "== 数据库 =="
if pg_isready >/dev/null 2>&1; then
  echo "  PostgreSQL: 可用"
  uv run alembic current 2>/dev/null | tail -1 || true
else
  echo "  PostgreSQL: 不可用"
fi

echo "== 模型 =="
if grep -q '^MODEL_API_KEY=..*' .env 2>/dev/null; then
  echo "  MODEL_API_KEY: 已设置（真实模型）"
else
  echo "  MODEL_API_KEY: 空（FakeModel；FAKE_MODEL_MODE=${FAKE_MODEL_MODE:-none}）"
fi

echo "== OpenAPI 类型 =="
./scripts/check-api-types.sh 2>&1 | tail -2
