#!/bin/sh
# 本地验证：依次执行后端与前端检查，任一失败即退出。
set -e
cd "$(git rev-parse --show-toplevel)"

echo "== ruff check =="
UV_CACHE_DIR=./.uv-cache uv run ruff check .

echo "== ruff format =="
UV_CACHE_DIR=./.uv-cache uv run ruff format --check .

echo "== mypy =="
UV_CACHE_DIR=./.uv-cache uv run mypy services

echo "== pytest =="
UV_CACHE_DIR=./.uv-cache uv run pytest

echo "== docs =="
python3 scripts/check-docs.py

echo "== web lint =="
pnpm -C apps/web lint

echo "== web format =="
pnpm -C apps/web exec prettier --check .

echo "== web typecheck =="
pnpm -C apps/web typecheck

echo "== web test =="
pnpm -C apps/web test
