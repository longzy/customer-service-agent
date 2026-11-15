#!/usr/bin/env bash
# 突变检查：只跑关键模块，不进 pre-commit。
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

MODULE="${1:-services.tools.policy}"

uv run mutmut run --max-children 4

RESULT=$(uv run mutmut results --all true 2>/dev/null | grep "$MODULE" || true)
KILLED=$(printf '%s\n' "$RESULT" | grep -c "killed" || true)
SURVIVED=$(printf '%s\n' "$RESULT" | grep -c "survived" || true)
TOTAL=$((KILLED + SURVIVED))
if [ "$TOTAL" -eq 0 ]; then
  echo "$MODULE：未生成突变体（检查 mutmut 配置）"
  exit 1
fi
SCORE=$(python3 -c "print(f'{$KILLED / $TOTAL * 100:.1f}')")
echo "$MODULE：killed=$KILLED survived=$SURVIVED total=$TOTAL score=${SCORE}%"
