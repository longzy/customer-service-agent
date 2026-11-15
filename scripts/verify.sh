#!/bin/sh
# 本地验证：依次执行后端与前端检查，任一失败即退出。
set -e
cd "$(git rev-parse --show-toplevel)"

echo "== ruff check =="
UV_CACHE_DIR=./.uv-cache uv run ruff check .

echo "== ruff format =="
UV_CACHE_DIR=./.uv-cache uv run ruff format --check .

echo "== prod import =="
uv run --no-dev python -c "import services.tools.gateway as g; g.ToolGateway([], g.OwnershipIndex())"

echo "== mypy =="
UV_CACHE_DIR=./.uv-cache uv run mypy services

echo "== pytest =="
UV_CACHE_DIR=./.uv-cache uv run pytest

echo "== route coverage =="
python3 scripts/check-route-coverage.py

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

echo "== 记录验证结果 =="
PYTEST_LINE=$(uv run pytest 2>&1 | grep -E "[0-9]+ passed" | tail -1)
MYPY_LINE=$(uv run mypy services 2>&1 | tail -1)
DOCS_LINE=$(python3 scripts/check-docs.py 2>&1 | tail -1)
python3 - "$PYTEST_LINE" "$MYPY_LINE" "$DOCS_LINE" <<'PY'
import sys
from pathlib import Path

pytest_line, mypy_line, docs_line = sys.argv[1:4]
pytest_count = next((part for part in pytest_line.split() if part.isdigit()), "?")
mypy_count = mypy_line.split(" ")[-3] if "source files" in mypy_line else "?"
import re

match = re.search(r"(\d+) 条 AC", docs_line)
ac_count = match.group(1) if match else "?"
summary = (
    f"- 最近验证：`./scripts/verify.sh` 全部检查通过——"
    f"pytest {pytest_count} passed、mypy {mypy_count} 个文件、"
    f"文档检查通过（{ac_count} 条 AC）、前端 lint/typecheck/test 通过"
)
path = Path("docs/CURRENT.md")
content = path.read_text(encoding="utf-8")
before, rest = content.split("<!-- verify:start -->", 1)
_, after = rest.split("<!-- verify:end -->", 1)
path.write_text(
    f"{before}<!-- verify:start -->\n{summary}\n<!-- verify:end -->{after}",
    encoding="utf-8",
)
print(summary)
PY
