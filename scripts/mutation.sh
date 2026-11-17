#!/usr/bin/env bash
# 突变检查：只覆盖关键模块，不进 pre-commit。
#
# 用法：
#   ./scripts/mutation.sh                    # 运行并检查全部关键模块
#   ./scripts/mutation.sh backend.tools     # 只检查某个模块
#   ./scripts/mutation.sh --report           # 只解析已有结果，不重新运行
#   ./scripts/mutation.sh --self-test        # 验证解析与阈值逻辑
#
# 突变范围由 pyproject.toml 的 [tool.mutmut] source_paths 决定，本脚本不维护
# 第二份范围清单；阈值与 docs/process/tdd.md 第 5 节一致。
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"
export ENVIRONMENT="${ENVIRONMENT:-development}"

threshold_for() { # $1=模块 → 阈值
  case "$1" in
    backend.workflows* | backend.tools*) echo 80 ;;
    backend.domain*) echo 70 ;;
    *) echo 80 ;;
  esac
}

count_status() { # $1=结果文本 $2=模块 $3=killed|survived
  printf '%s\n' "$1" \
    | grep -E "(^|[./])${2//./\\.}([.:]|/)" \
    | grep -cE "(^|[^a-z])$3([^a-z]|$)" || true
}

score_line() { # $1=结果文本 $2=模块 → "killed survived score threshold status"
  local killed survived total score threshold status
  killed=$(count_status "$1" "$2" killed)
  survived=$(count_status "$1" "$2" survived)
  total=$((killed + survived))
  threshold=$(threshold_for "$2")
  if [ "$total" -eq 0 ]; then
    echo "0 0 - $threshold 未生成突变体"
    return
  fi
  score=$(python3 -c "print(f'{$killed / $total * 100:.1f}')")
  status="通过"
  if python3 -c "import sys; sys.exit(0 if $score < $threshold else 1)"; then
    status="未达标"
  fi
  echo "$killed $survived $score $threshold $status"
}

self_test() {
  local sample out
  sample=$'backend.tools.policy.x__mutmut_1: killed\nbackend.tools.policy.x__mutmut_2: survived\nbackend.tools.policy.x__mutmut_3: killed'
  out=$(score_line "$sample" backend.tools.policy)
  [ "$out" = "2 1 66.7 80 未达标" ] || { echo "自检失败：$out"; exit 1; }
  out=$(score_line "$sample" backend.domain.orders)
  [ "$out" = "0 0 - 70 未生成突变体" ] || { echo "自检失败：$out"; exit 1; }
  [ "$(threshold_for backend.workflows.cancel)" = "80" ] || { echo "自检失败：阈值"; exit 1; }
  [ "$(threshold_for backend.domain.orders)" = "70" ] || { echo "自检失败：阈值"; exit 1; }
  echo "mutation.sh 自检通过"
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit 0
fi

if [ "${1:-}" != "--report" ]; then
  echo "== 运行突变检查（范围见 pyproject.toml [tool.mutmut] source_paths）=="
  uv run mutmut run --max-children 4
fi

RESULTS=$(uv run mutmut results --all true 2>/dev/null | sed 's/^[[:space:]]*//' || true)
if [ -z "$RESULTS" ]; then
  echo "没有可解析的突变结果；先运行 ./scripts/mutation.sh" >&2
  exit 1
fi

FILTER="${1:-}"
[ "$FILTER" = "--report" ] && FILTER=""

MODULES=$(printf '%s\n' "$RESULTS" | grep -oE '^backend(\.[a-z_]+){1,2}' | sort -u)
FAILED=0
COUNTED=0
for module in $MODULES; do
  if [ -n "$FILTER" ] && [[ "$module" != "$FILTER"* ]]; then
    continue
  fi
  read -r killed survived score threshold status <<<"$(score_line "$RESULTS" "$module")"
  [ "$score" = "-" ] && continue
  COUNTED=$((COUNTED + 1))
  [ "$status" = "未达标" ] && FAILED=1
  printf '%-40s killed=%-4s survived=%-4s score=%s%% 阈值=%s%% %s\n' \
    "$module" "$killed" "$survived" "$score" "$threshold" "$status"
done

if [ "$COUNTED" -eq 0 ]; then
  echo "没有匹配的突变结果，检查模块名或先运行突变检查。" >&2
  exit 1
fi

if [ "$FAILED" -eq 1 ]; then
  echo "存在未达标的突变分数：在任务卡说明是测试过弱还是真实缺口。" >&2
  exit 1
fi
