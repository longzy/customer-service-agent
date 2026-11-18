#!/bin/sh
# 本地/CI 统一验证入口。默认只输出一行摘要；失败时打印失败步骤与日志尾部。
# 用法：
#   ./scripts/verify.sh              # 全量验证并回写 docs/CURRENT.md 的验证块
#   ./scripts/verify.sh --verbose    # 逐步输出完整日志
#   ./scripts/verify.sh --no-record  # 只验证，不修改仓库（CI 使用）
#   ./scripts/verify.sh --fast       # 后端快速反馈：ruff/format/mypy/unit，不写状态
# 前端步骤包含 lint/format/typecheck/test/build（build 与 CI frontend-build job 对齐）。
set -e
cd "$(git rev-parse --show-toplevel)"

export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"
RECORD=1
FAST=0
VERBOSE=0
for arg in "$@"; do
  case "$arg" in
    --no-record) RECORD=0 ;;
    --fast) FAST=1 ;;
    --verbose) VERBOSE=1 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

STEP_LOG=$(mktemp)
PYTEST_LOG=$(mktemp)
EVAL_LOG=$(mktemp)
MYPY_LOG=$(mktemp)
DOCS_LOG=$(mktemp)
TRACE_LOG=$(mktemp)
trap 'rm -f "$STEP_LOG" "$PYTEST_LOG" "$EVAL_LOG" "$MYPY_LOG" "$DOCS_LOG" "$TRACE_LOG"' EXIT

run_step() {
  label=$1
  shift
  if ! "$@" >"$STEP_LOG" 2>&1; then
    echo "验证失败：$label" >&2
    tail -40 "$STEP_LOG" >&2
    exit 1
  fi
  if [ "$VERBOSE" = "1" ]; then
    echo "== $label =="
    cat "$STEP_LOG"
  fi
}

if [ "$FAST" = "1" ]; then
  run_step "ruff check" uv run ruff check .
  run_step "ruff format" uv run ruff format --check .
  run_step "mypy" uv run mypy backend
  run_step "shell 检查" uv run python scripts/check-shell.py
  run_step "命令冒烟" ./scripts/check-commands.sh
  run_step "import 边界" python3 scripts/check-imports.py --strict
  run_step "unit tests（独立测试库）" ./scripts/test-db.sh tests/unit -q
  echo "fast checks passed"
  exit 0
fi

REPORTS_DIR="evals/reports"
JUNIT="$REPORTS_DIR/latest-junit.xml"
mkdir -p "$REPORTS_DIR"

run_step "ruff check" uv run ruff check .
run_step "ruff format" uv run ruff format --check .
run_step "shell 检查" uv run python scripts/check-shell.py
run_step "命令冒烟" ./scripts/check-commands.sh
run_step "import 边界" python3 scripts/check-imports.py --strict
run_step "prod import" env ENVIRONMENT=test MODEL_API_KEY='' uv run --no-dev python -c \
  "import backend.api.main, backend.tools.gateway, backend.adapters.oms.factory"
run_step "密钥扫描" python3 scripts/check-secrets.py
run_step "mypy" uv run mypy backend
cp "$STEP_LOG" "$MYPY_LOG"
run_step "契约生成物" ./scripts/check-contracts.sh

# pytest 失败也要继续生成 eval 报告，因此这里暂时关闭 set -e 并分别记退出码。
if [ "$VERBOSE" = "1" ]; then
  echo "== pytest（独立测试库）=="
fi
rm -f "$JUNIT"
set +e
./scripts/test-db.sh -q --junitxml="$JUNIT" >"$PYTEST_LOG" 2>&1
PYTEST_STATUS=$?
set -e
if [ "$PYTEST_STATUS" -ne 0 ]; then
  echo "pytest 失败" >&2
  tail -40 "$PYTEST_LOG" >&2
elif [ "$VERBOSE" = "1" ]; then
  tail -1 "$PYTEST_LOG"
fi

if [ "$VERBOSE" = "1" ]; then
  echo "== 场景评测（复用 pytest JUnit）=="
fi
set +e
uv run python evals/run.py --junit "$JUNIT" --reports-dir "$REPORTS_DIR" >"$EVAL_LOG" 2>&1
EVAL_STATUS=$?
set -e
if [ "$EVAL_STATUS" -ne 0 ]; then
  echo "场景评测失败" >&2
  tail -40 "$EVAL_LOG" >&2
fi
if [ "$PYTEST_STATUS" -ne 0 ] || [ "$EVAL_STATUS" -ne 0 ]; then
  echo "pytest/eval 失败：pytest=$PYTEST_STATUS eval=$EVAL_STATUS" >&2
  exit 1
fi

run_step "route coverage" python3 scripts/check-route-coverage.py
run_step "追溯矩阵" python3 scripts/trace.py --strict
cp "$STEP_LOG" "$TRACE_LOG"
run_step "当前状态一致性" python3 scripts/check-status.py
run_step "docs" python3 scripts/check-docs.py
cp "$STEP_LOG" "$DOCS_LOG"
run_step "设计令牌" ./scripts/check-tokens.sh
run_step "chat lint" pnpm -C apps/chat lint
run_step "chat format" pnpm -C apps/chat exec prettier --check .
run_step "chat typecheck" pnpm -C apps/chat typecheck
run_step "chat test" pnpm -C apps/chat test
run_step "workspace lint" pnpm -C apps/workspace lint
run_step "workspace format" pnpm -C apps/workspace exec prettier --check .
run_step "workspace typecheck" pnpm -C apps/workspace typecheck
run_step "workspace test" pnpm -C apps/workspace test
run_step "chat build" pnpm -C apps/chat build
run_step "workspace build" pnpm -C apps/workspace build

PYTEST_LINE=$(grep -E "[0-9]+ passed" "$PYTEST_LOG" | tail -1)
MYPY_LINE=$(tail -1 "$MYPY_LOG")
DOCS_LINE=$(tail -1 "$DOCS_LOG")
TRACE_LINE=$(tail -1 "$TRACE_LOG")
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
