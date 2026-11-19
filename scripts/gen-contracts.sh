#!/bin/sh
# 一次重生成所有契约派生物与测试快照；改错误码/路由响应/表结构后运行。
# 只写生成物，不改事实源；提交前用 check-contracts.sh（或 pre-commit）校验。
set -e
cd "$(git rev-parse --show-toplevel)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

uv run python scripts/gen_domain_contract.py
uv run python scripts/gen_tool_openapi.py
uv run python scripts/export_openapi.py
pnpm -C packages/contracts generate
uv run python scripts/gen_test_fixtures.py

echo "已生成契约与测试快照：packages/contracts、apps/*/lib/api-types.ts、tests/fixtures/*-r0-2.json"
