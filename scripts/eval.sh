#!/bin/sh
# 场景评测唯一入口：先跑 pytest（独立测试库）并写 JUnit，再聚合 AC 报告。
# pytest 失败也生成报告；pytest 与 eval 任一失败则退出 1。
set +e
cd "$(git rev-parse --show-toplevel)" || exit 1

export UV_CACHE_DIR="${UV_CACHE_DIR:-./.uv-cache}"
REPORTS_DIR="evals/reports"
JUNIT="$REPORTS_DIR/latest-junit.xml"

mkdir -p "$REPORTS_DIR"
# 避免上一次的 JUnit 在本次 pytest 早期失败时被误当成结果
rm -f "$JUNIT"

./scripts/test-db.sh -q --junitxml="$JUNIT"
PYTEST_STATUS=$?

uv run python evals/run.py --junit "$JUNIT" --reports-dir "$REPORTS_DIR"
EVAL_STATUS=$?

if [ "$PYTEST_STATUS" -ne 0 ] || [ "$EVAL_STATUS" -ne 0 ]; then
  echo "场景评测失败：pytest=$PYTEST_STATUS eval=$EVAL_STATUS" >&2
  exit 1
fi

echo "场景评测通过：pytest=0 eval=0"
exit 0
