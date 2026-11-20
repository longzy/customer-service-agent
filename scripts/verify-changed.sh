#!/bin/sh
# 实现内环：按变更范围跑定向检查，不是门禁。
# 全量 pytest/评测/前端构建仍由评审门禁与收口执行：make verify-check / make verify。
# 用法：./scripts/verify-changed.sh [F-08] [--base=<ref>] [--paths-file=<file>] [--dry-run]
#   --paths-file 用文件中的路径清单代替 git diff（每行一个，便于只验证本次改动或自测）
#   --dry-run    只打印将运行/跳过的检查，不执行
set -e
cd "$(git rev-parse --show-toplevel)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"

FEATURE=""
BASE="HEAD"
PATHS_FILE=""
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    F-[0-9][0-9]) FEATURE=$arg ;;
    --base=*) BASE=${arg#--base=} ;;
    --paths-file=*) PATHS_FILE=${arg#--paths-file=} ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "用法：./scripts/verify-changed.sh [F-08] [--base=<ref>] [--paths-file=<file>] [--dry-run]"
      echo "  默认 feature 取 CURRENT.md「当前工作」的第一个 F-xx；默认 base=HEAD（未提交变更）。"
      echo "  --paths-file 用文件中的路径清单代替 git diff（路径相对仓库根）；--dry-run 只打印计划。"
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

if [ -n "$PATHS_FILE" ]; then
  if [ ! -f "$PATHS_FILE" ]; then
    echo "路径清单不存在：$PATHS_FILE" >&2
    exit 2
  fi
  CHANGED=$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' "$PATHS_FILE" | grep -v '^$' | sort -u || true)
else
  CHANGED=$( { git diff --name-only "$BASE"; git ls-files --others --exclude-standard; } | sort -u )
fi

changed_matches() {
  [ -n "$CHANGED" ] && printf '%s\n' "$CHANGED" | grep -Eq "$1"
}

count_changed() {
  printf '%s\n' "$CHANGED" | grep -c . || true
}

# 变更分类：每一类只触发对应检查。
# Python 侧（ruff）：后端、测试、迁移、脚本、评测与 Python 配置。
PYTHON_CHANGED=0
if changed_matches '^(backend/|tests/|migrations/|scripts/|evals/|conftest\.py$|pyproject\.toml$)'; then PYTHON_CHANGED=1; fi
# 后端测试：业务代码、测试、迁移。
BACKEND_CHANGED=0
if changed_matches '^(backend/|tests/|migrations/|conftest\.py$)'; then BACKEND_CHANGED=1; fi
# 后端类型：只看业务代码与 Python 配置，测试变更不影响 mypy 结果。
MYPY_CHANGED=0
if changed_matches '^(backend/|conftest\.py$|pyproject\.toml$)'; then MYPY_CHANGED=1; fi
# 前端：按 app 分别触发，互不牵连。
CHAT_CHANGED=0
if changed_matches '^apps/chat/'; then CHAT_CHANGED=1; fi
WORKSPACE_CHANGED=0
if changed_matches '^apps/workspace/'; then WORKSPACE_CHANGED=1; fi
# 文档：文档正文、根目录说明文件。
DOCS_CHANGED=0
if changed_matches '^(docs/|README\.md$|AGENTS\.md$|CLAUDE\.md$|CONTRIBUTING\.md$|GEMINI\.md$|SECURITY\.md$)'; then DOCS_CHANGED=1; fi
# 状态与评审一致性：CURRENT、specs、reviews。
STATUS_CHANGED=0
if changed_matches '^(docs/CURRENT\.md$|docs/specs/|docs/reviews/)'; then STATUS_CHANGED=1; fi
# 追溯：AC 覆盖来自 specs/tests。
TRACE_CHANGED=0
if changed_matches '^(docs/|tests/)'; then TRACE_CHANGED=1; fi
# 契约：契约源、生成物与生成脚本。
CONTRACTS_CHANGED=0
if changed_matches '^(packages/contracts/|apps/(chat|workspace)/lib/api-types\.ts$|tests/fixtures/|scripts/gen-contracts\.sh$|scripts/gen_test_fixtures\.py$|scripts/check-contracts\.sh$)'; then CONTRACTS_CHANGED=1; fi
# 评审前置：前端结构基线 / trace 基线 / CURRENT 评审声称。
REVIEW_CHANGED=0
if changed_matches '^(apps/|docs/|scripts/frontend-structure-baseline\.txt$|scripts/trace-baseline\.txt$)'; then REVIEW_CHANGED=1; fi

plan() {
  flag=$1
  label=$2
  if [ "$flag" -eq 1 ]; then
    echo "运行：$label"
  else
    echo "跳过：${label}（无相关变更）"
  fi
  [ "$flag" -eq 1 ]
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

echo "== 变更范围：$(count_changed) 个文件 =="
plan "$PYTHON_CHANGED" "Python 静态检查（ruff）" || true
plan "$MYPY_CHANGED" "后端类型检查（mypy）" || true
plan "$REVIEW_CHANGED" "评审前置检查" || true
plan "$DOCS_CHANGED" "文档引用" || true
plan "$STATUS_CHANGED" "状态一致性" || true
plan "$TRACE_CHANGED" "追溯矩阵" || true
plan "$CONTRACTS_CHANGED" "契约生成物" || true
plan "$BACKEND_CHANGED" "后端测试" || true
plan "$CHAT_CHANGED" "chat 前端" || true
plan "$WORKSPACE_CHANGED" "workspace 前端" || true

if [ "$DRY_RUN" -eq 1 ]; then
  echo "verify-changed 计划：feature=${FEATURE:-未指定}，$(count_changed) 个文件；未执行检查。"
  exit 0
fi

if [ "$PYTHON_CHANGED" -eq 1 ]; then
  echo "== Python 静态检查 =="
  uv run ruff check . --quiet
  uv run ruff format --check . --quiet
fi

if [ "$MYPY_CHANGED" -eq 1 ]; then
  echo "== 后端类型检查 =="
  uv run mypy backend
fi

if [ "$REVIEW_CHANGED" -eq 1 ]; then
  echo "== 评审前置检查 =="
  python3 scripts/check-review-prereqs.py
fi

if [ "$DOCS_CHANGED" -eq 1 ]; then
  echo "== 文档引用 =="
  run_quiet "文档引用" python3 scripts/check-docs.py
fi

if [ "$STATUS_CHANGED" -eq 1 ]; then
  echo "== 状态一致性 =="
  run_quiet "状态一致性" python3 scripts/check-status.py
fi

if [ "$TRACE_CHANGED" -eq 1 ]; then
  echo "== 追溯矩阵 =="
  run_quiet "追溯矩阵" python3 scripts/trace.py --strict
fi

if [ "$CONTRACTS_CHANGED" -eq 1 ]; then
  echo "== 契约生成物 =="
  run_quiet "契约生成物" ./scripts/check-contracts.sh
fi

AC_FILTER=$(printf '%s' "$ACS" | sed 's/AC-/AC_/g')

if [ "$BACKEND_CHANGED" -eq 1 ]; then
  if [ -n "$AC_FILTER" ]; then
    echo "== AC 定向测试：$ACS =="
    ./scripts/test-db.sh -k "$AC_FILTER" -q
  else
    echo "== 后端单元测试 =="
    ./scripts/test-db.sh tests/unit -q
  fi
fi

if [ "$CHAT_CHANGED" -eq 1 ]; then
  echo "== chat 前端 =="
  pnpm -C apps/chat lint
  pnpm -C apps/chat exec prettier --check .
  pnpm -C apps/chat typecheck
  pnpm -C apps/chat test
fi

if [ "$WORKSPACE_CHANGED" -eq 1 ]; then
  echo "== workspace 前端 =="
  pnpm -C apps/workspace lint
  pnpm -C apps/workspace exec prettier --check .
  pnpm -C apps/workspace typecheck
  pnpm -C apps/workspace test
fi

echo "verify-changed 通过：feature=${FEATURE:-未指定}，变更 $(count_changed) 个文件；未跑全量 pytest/评测/构建，门禁请用 make verify-check。"
