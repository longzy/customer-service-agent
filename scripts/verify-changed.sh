#!/bin/sh
# 实现内环：按变更范围跑定向检查，不是门禁。
# 全量 pytest/评测/前端构建仍由评审门禁与收口执行：make verify-check / make verify。
# 用法：./scripts/verify-changed.sh [F-08] [--base=<ref>]
set -e
cd "$(git rev-parse --show-toplevel)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

FEATURE=""
BASE="HEAD"
for arg in "$@"; do
  case "$arg" in
    F-[0-9][0-9]) FEATURE=$arg ;;
    --base=*) BASE=${arg#--base=} ;;
    -h|--help)
      echo "用法：./scripts/verify-changed.sh [F-08] [--base=<ref>]"
      echo "  默认 feature 取 CURRENT.md「当前工作」的第一个 F-xx；默认 base=HEAD（未提交变更）。"
      exit 0
      ;;
    *)
      echo "未知参数：$arg" >&2
      exit 2
      ;;
  esac
done

if [ -z "$FEATURE" ]; then
  FEATURE=$(grep '^- 当前工作：' docs/CURRENT.md | grep -o 'F-[0-9][0-9]' | head -1 || true)
fi

ACS=""
if [ -n "$FEATURE" ]; then
  ACS=$(python3 - "$FEATURE" <<'PY'
import re
import sys
from pathlib import Path

feature = sys.argv[1]
for path in sorted(Path("docs/specs").glob("*/features.md")):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| {feature} |"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 6:
                acs = list(dict.fromkeys(re.findall(r"AC-\d{2}", cells[4])))
                print(" or ".join(acs))
                raise SystemExit(0)
raise SystemExit(1)
PY
) || ACS=""
fi

CHANGED=$( { git diff --name-only "$BASE"; git ls-files --others --exclude-standard; } | sort -u )

changed_matches() {
  [ -n "$CHANGED" ] && printf '%s\n' "$CHANGED" | grep -Eq "$1"
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

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

echo "== 静态检查 =="
uv run ruff check . --quiet
uv run ruff format --check . --quiet
uv run mypy backend
python3 scripts/check-review-prereqs.py

echo "== 文档/状态/追溯/契约 =="
run_quiet "文档引用" python3 scripts/check-docs.py
run_quiet "状态一致性" python3 scripts/check-status.py
run_quiet "追溯矩阵" python3 scripts/trace.py --strict
run_quiet "契约生成物" ./scripts/check-contracts.sh

AC_FILTER=$(printf '%s' "$ACS" | sed 's/AC-/AC_/g')

if [ -n "$AC_FILTER" ] && changed_matches '^(backend/|tests/|migrations/)'; then
  echo "== AC 定向测试：$ACS =="
  ./scripts/test-db.sh -k "$AC_FILTER" -q
elif changed_matches '^(backend/|tests/|migrations/)'; then
  echo "== 后端单元测试 =="
  ./scripts/test-db.sh tests/unit -q
fi

if changed_matches '^apps/chat/'; then
  echo "== chat 前端 =="
  pnpm -C apps/chat lint
  pnpm -C apps/chat exec prettier --check .
  pnpm -C apps/chat typecheck
  pnpm -C apps/chat test
fi

if changed_matches '^apps/workspace/'; then
  echo "== workspace 前端 =="
  pnpm -C apps/workspace lint
  pnpm -C apps/workspace exec prettier --check .
  pnpm -C apps/workspace typecheck
  pnpm -C apps/workspace test
fi

count=$(printf '%s\n' "$CHANGED" | grep -c . || true)
echo "verify-changed 通过：feature=${FEATURE:-未指定}，变更 ${count} 个文件；未跑全量 pytest/评测/构建，门禁请用 make verify-check。"
