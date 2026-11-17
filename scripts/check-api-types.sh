#!/bin/sh
# 校验 OpenAPI 快照与前端生成类型均是最新；不修改仓库文件。
set -e
cd "$(git rev-parse --show-toplevel)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

uv run python scripts/export_openapi.py --check

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
pnpm -C packages/contracts exec openapi-typescript openapi.json -o "$TMP_DIR/api-types.ts" >/dev/null
if ! diff -u apps/chat/lib/api-types.ts "$TMP_DIR/api-types.ts"; then
  echo "前端类型与 OpenAPI 不一致：请运行 pnpm -C packages/contracts generate" >&2
  exit 1
fi
echo "前端类型与 OpenAPI 一致：apps/chat/lib/api-types.ts"
