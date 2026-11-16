#!/usr/bin/env bash
# 每个任务只跑一次全量 mutation；重跑需显式 --force 并在执行卡写原因。
# 用法：./scripts/mutation-once.sh T-13 [mutation.sh 参数]
set -euo pipefail
cd "$(dirname "$0")/.."

TASK="${1:-}"
shift || true
if [ -z "$TASK" ]; then
  echo "用法：./scripts/mutation-once.sh <任务号> [mutation.sh 参数]" >&2
  exit 2
fi

FORCE=0
if [ "${1:-}" = "--force" ]; then
  FORCE=1
  shift
fi
for arg in "$@"; do
  case "$arg" in
    --report | --changed | --self-test)
      echo "mutation-once 只执行全量 mutation；$arg 请直接调用 mutation.sh。" >&2
      exit 2
      ;;
  esac
done

STAMP_DIR=".mutation-runs"
STAMP="$STAMP_DIR/$TASK.done"
mkdir -p "$STAMP_DIR"
if [ -f "$STAMP" ] && [ "$FORCE" = "0" ]; then
  echo "任务 $TASK 已跑过全量 mutation（$STAMP）；重跑请加 --force 并在执行卡写原因。" >&2
  exit 1
fi

./scripts/mutation.sh "$@"
touch "$STAMP"
echo "已记录：$TASK 全量 mutation 完成（$STAMP）"
