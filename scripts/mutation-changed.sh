#!/usr/bin/env bash
# 只对本次改动的核心模块跑突变。
# 用法：./scripts/mutation-changed.sh
# 范围：services/tools、services/workflows、services/api/domain 下变更/新增的 .py。
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"
export MODEL_API_KEY="${MODEL_API_KEY:-test-key}"

CHANGED_FILES=$(
  {
    git diff --name-only -- services/tools services/workflows services/api/domain
    git ls-files --others --exclude-standard -- services/tools services/workflows services/api/domain
  } | grep -E '\.py$' | while read -r path; do [ -f "$path" ] && printf '%s\n' "$path"; done | sort -u || true
)
if [ -z "$CHANGED_FILES" ]; then
  echo "没有改动的核心模块，跳过突变。"
  exit 0
fi

BACKUP=$(mktemp)
cp pyproject.toml "$BACKUP"
restore() {
  if [ -f "$BACKUP" ]; then
    mv "$BACKUP" pyproject.toml
  fi
}
trap restore EXIT INT TERM

python3 - "$CHANGED_FILES" <<'PY'
import sys
from pathlib import Path

paths = [line.strip() for line in sys.argv[1].splitlines() if line.strip()]
array = ", ".join(f'"{path}"' for path in paths)
text = Path("pyproject.toml").read_text(encoding="utf-8")
needle = 'source_paths = ["services/tools", "services/workflows", "services/api/domain"]'
if needle not in text:
    raise SystemExit("找不到 source_paths 配置")
Path("pyproject.toml").write_text(text.replace(needle, needle + f"\nonly_mutate = [{array}]", 1), encoding="utf-8")
PY

echo "== 按改动模块运行突变 =="
printf '%s\n' "$CHANGED_FILES"
rm -rf mutants .mutmut-cache
uv run mutmut run --max-children 4
restore
trap - EXIT INT TERM
echo "== 报告（本次改动模块）=="
./scripts/mutation.sh --report
