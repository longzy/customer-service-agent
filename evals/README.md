# evals

场景评测集与报告。评测固定、离线，只使用脚本化 `FakeModelClient` 与 Mock OMS；
真实模型质量另列趋势，不进 M1 门禁。

## 覆盖

- **AC 聚合报告**：`evals/run.py` 解析 pytest JUnit，按测试名里的 `_AC_XX` 聚合 AC-01 至 AC-21，输出通过/失败与测试数。
- **多轮场景**：`tests/integration/test_eval_scenarios.py` 用 2–3 条脚本化场景覆盖查询、歧义澄清与取消意图，测试名带 AC 后缀，自动进入同一份报告。
- 不重复 confirm/故障/响应头/日志测试；这些由既有 pytest 覆盖。

## 运行

```bash
./scripts/eval.sh
```

唯一入口。它先用 `./scripts/test-db.sh` 在独立测试库跑全部 pytest 并写
`evals/reports/latest-junit.xml`，再调用 `evals/run.py` 生成报告。
`set +e` 保证 pytest 失败时仍写报告；pytest 与 eval 任一失败都退出 1。

`./scripts/verify.sh` 复用同一 JUnit，不重复跑测试；pytest 失败也生成报告。

只重跑报告生成器（不执行测试）：

```bash
uv run python evals/run.py \
  --junit evals/reports/latest-junit.xml \
  --reports-dir evals/reports
```

- `--junit`：JUnit XML 路径，默认 `<reports-dir>/latest-junit.xml`。
- `--reports-dir`：报告目录，默认 `evals/reports`。

## 输出

- `evals/reports/latest.json`：每次覆盖；含 AC 状态、测试数、失败测试名、多轮场景耗时。
- `evals/reports/latest.md`：同一份结果的可读版本。
- `evals/reports/<timestamp>.json`：带时间戳的历史报告，失败也写。
- `evals/reports/` 已加入 `.gitignore`，报告由命令再生成。

## 失败条件

以下任一情况 `evals/run.py` 退出 1，并仍写出失败报告：

- 缺少任一 AC-01 至 AC-21；
- JUnit 中没有测试用例；
- JUnit 无法解析或文件不存在；
- 任一测试失败，或被跳过（跳过不算通过）。
