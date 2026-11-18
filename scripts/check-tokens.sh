#!/bin/sh
# 校验两个前端的令牌副本与唯一来源一致；禁止漂移。
set -e
cd "$(git rev-parse --show-toplevel)"
for app in chat workspace; do
  if ! diff -q docs/design-system/tokens.css "apps/$app/app/tokens.css" >/dev/null 2>&1; then
    echo "设计令牌不一致：apps/$app/app/tokens.css" >&2
    echo "修复：cp docs/design-system/tokens.css apps/$app/app/tokens.css" >&2
    exit 1
  fi
done
echo "设计令牌一致：docs/design-system/tokens.css -> apps/*/app/tokens.css"
