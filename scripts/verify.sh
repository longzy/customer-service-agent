#!/bin/sh
# 本地/CI 统一验证入口。每一步跑一次，结果写入一份摘要。
# 用法：
#   ./scripts/verify.sh             # 全量验证并回写 docs/CURRENT.md 的验证块
#   ./scripts/verify.sh --no-record # 只验证，不修改仓库（CI 使用）
#   ./scripts/verify.sh --fast      # 后端快速反馈：ruff/format/mypy/unit，不写状态
set -e
cd "$(git rev-parse --show-toplevel)"

export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"
RECORD=1
FAST=0
for arg in "$@"; do
  case "$arg" in
    --no-record) RECORD=0 ;;
    --fast) FAST=1 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

if [ "$FAST" = "1" ]; then
  echo "== fast: ruff check =="
  uv run ruff check .
  echo "== fast: ruff format =="
  uv run ruff format --check .
  echo "== fast: mypy =="
  uv run mypy services
  echo "== fast: unit tests（独立测试库）=="
  ./scripts/test-db.sh tests/unit -q
  echo "fast checks passed"
  exit 0
fi

PYTEST_LOG=$(mktemp)
trap 'rm -f "$PYTEST_LOG"' EXIT
REPORTS_DIR="evals/reports"
JUNIT="$REPORTS_DIR/latest-junit.xml"
mkdir -p "$REPORTS_DIR"

echo "== ruff check =="
uv run ruff check .

echo "== ruff format =="
uv run ruff format --check .

echo "== prod import =="
uv run --no-dev python -c "import services.tools.gateway as g; g.ToolGateway([], g.OwnershipIndex())"

echo "== 密钥扫描 =="
python3 scripts/check-secrets.py

echo "== mypy =="
uv run mypy services

echo "== pytest（独立测试库）=="
# pytest 失败也要继续生成 eval 报告，因此这里暂时关闭 set -e 并分别记退出码
rm -f "$JUNIT"
set +e
./scripts/test-db.sh -q --junitxml="$JUNIT" >"$PYTEST_LOG" 2>&1
PYTEST_STATUS=$?
set -e
if [ "$PYTEST_STATUS" -ne 0 ]; then
  tail -40 "$PYTEST_LOG"
else
  tail -1 "$PYTEST_LOG"
fi

echo "== 场景评测（复用 pytest JUnit）=="
set +e
uv run python evals/run.py --junit "$JUNIT" --reports-dir "$REPORTS_DIR"
EVAL_STATUS=$?
set -e
if [ "$PYTEST_STATUS" -ne 0 ] || [ "$EVAL_STATUS" -ne 0 ]; then
  echo "pytest/eval 失败：pytest=$PYTEST_STATUS eval=$EVAL_STATUS" >&2
  exit 1
fi

echo "== route coverage =="
python3 scripts/check-route-coverage.py

echo "== 追溯矩阵 =="
python3 scripts/trace.py --strict

echo "== 当前状态一致性 =="
python3 scripts/check-status.py

echo "== docs =="
python3 scripts/check-docs.py

echo "== web lint =="
pnpm -C apps/web lint

echo "== web format =="
pnpm -C apps/web exec prettier --check .

echo "== web typecheck =="
pnpm -C apps/web typecheck

echo "== web test =="
pnpm -C apps/web test

PYTEST_LINE=$(grep -E "[0-9]+ passed" "$PYTEST_LOG" | tail -1)
MYPY_LINE=$(uv run mypy services 2>&1 | tail -1)
DOCS_LINE=$(python3 scripts/check-docs.py 2>&1 | tail -1)
TRACE_LINE=$(python3 scripts/trace.py 2>&1 | tail -1)
python3 - "$PYTEST_LINE" "$MYPY_LINE" "$DOCS_LINE" "$TRACE_LINE" "$RECORD" <<'PY'
import re
import sys
from pathlib import Path

pytest_line, mypy_line, docs_line, trace_line, record = sys.argv[1:6]
pytest_count = next((part for part in pytest_line.split() if part.isdigit()), "?")
mypy_count = mypy_line.split(" ")[-3] if "source files" in mypy_line else "?"
match = re.search(r"(\d+) 条 AC", docs_line)
ac_count = match.group(1) if match else "?"
summary = (
    f"- 最近验证：`./scripts/verify.sh` 全部检查通过——"
    f"pytest {pytest_count} passed（独立测试库）、mypy {mypy_count} 个文件、"
    f"追溯矩阵通过（{ac_count} 条 AC）、文档与前端检查通过"
)
print(summary)
if record != "1":
    print("（--no-record：未写入 docs/CURRENT.md）")
    raise SystemExit(0)

path = Path("docs/CURRENT.md")
content = path.read_text(encoding="utf-8")
before, rest = content.split("<!-- verify:start -->", 1)
_, after = rest.split("<!-- verify:end -->", 1)
path.write_text(
    f"{before}<!-- verify:start -->\n{summary}\n<!-- verify:end -->{after}",
    encoding="utf-8",
)
PY
