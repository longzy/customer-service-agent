#!/bin/sh
# 校验 `make help` 宣传的每个命令都有真实 recipe；防止 .PHONY 空 target 假成功。
set -e
cd "$(git rev-parse --show-toplevel)"

COMMANDS=$(make -s help | awk '/^make / {print $2}' | sort -u)
if [ -z "$COMMANDS" ]; then
  echo "make help 没有列出任何命令" >&2
  exit 1
fi

FAILED=0
for command in $COMMANDS; do
  output=$(make -n "$command" 2>&1 || true)
  case "$output" in
    *"Nothing to be done"*)
      echo "make help 列出 '$command'，但 Makefile 没有对应 recipe" >&2
      FAILED=1
      ;;
  esac
done

if [ "$FAILED" -eq 0 ]; then
  count=$(printf '%s\n' "$COMMANDS" | wc -l | tr -d ' ')
  echo "命令冒烟检查通过：make help 的 $count 个命令均有 recipe"
fi
exit "$FAILED"
