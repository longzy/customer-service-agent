#!/bin/sh
# 校验所有契约派生物与事实源一致；不修改仓库文件。
# 链路：backend.domain.errors → domain.json 错误码片段 → tools/openapi.json
#       → FastAPI openapi.json → 两个前端的 api-types.ts
set -e
cd "$(git rev-parse --show-toplevel)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

uv run python scripts/gen_domain_contract.py --check
uv run python scripts/gen_tool_openapi.py --check
uv run python scripts/export_openapi.py --check

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
for app in chat workspace; do
  pnpm -C packages/contracts exec openapi-typescript openapi.json -o "$TMP_DIR/api-types-$app.ts" >/dev/null
  if ! diff -u "apps/$app/lib/api-types.ts" "$TMP_DIR/api-types-$app.ts"; then
    echo "前端类型与 OpenAPI 不一致：请运行 pnpm -C packages/contracts generate" >&2
    exit 1
  fi
  echo "前端类型与 OpenAPI 一致：apps/$app/lib/api-types.ts"
done

uv run python scripts/gen_test_fixtures.py --check

echo "契约生成物一致：domain.json、tools/openapi.json、openapi.json、api-types.ts、tests/fixtures"
