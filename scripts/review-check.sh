#!/bin/sh
# 评审前置快检：机械规则 + 文档/状态/追溯/令牌/契约；不跑 pytest 与前端构建。
# 这不是全量门禁；全量由收口 make verify 与 CI 执行。
set -e
cd "$(git rev-parse --show-toplevel)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

python3 scripts/check-review-prereqs.py

run_quiet() {
  label=$1
  shift
  if "$@" >"$work/out" 2>&1; then
    echo "通过：$label"
  else
    echo "失败：$label" >&2
    tail -40 "$work/out" >&2
    exit 1
  fi
}

run_quiet "文档引用" python3 scripts/check-docs.py
run_quiet "任务索引同步" python3 scripts/gen_tasks.py --check
run_quiet "看板同步" python3 scripts/gen_board.py --check
run_quiet "状态一致性" python3 scripts/check-status.py
run_quiet "追溯矩阵" python3 scripts/trace.py --strict
run_quiet "设计令牌" ./scripts/check-tokens.sh
run_quiet "契约生成物" ./scripts/check-contracts.sh

echo "review-check 通过：机械前置、文档、状态、追溯、令牌与契约一致；全量由收口 make verify 与 CI 执行。"
