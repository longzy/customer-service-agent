#!/bin/sh
# 前端样式强制点：tokens 之外禁止颜色字面量、!important 与 id 选择器。
set -e
cd "$(git rev-parse --show-toplevel)"
for app in chat workspace; do
  echo "== stylelint apps/$app =="
  pnpm -C "apps/$app" exec stylelint "app/**/*.css"
done
echo "样式检查通过：tokens/无 !important/id/颜色字面量"
