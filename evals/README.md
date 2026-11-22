# evals

场景评测集与报告。评测固定、离线，只使用脚本化 `FakeModelClient` 与 Mock OMS；
真实模型质量另列趋势，不进 M1 门禁。

## 覆盖

- **AC 聚合报告**：`evals/run.py` 解析 pytest JUnit，按测试名里的 `_AC_XX` 聚合。
  AC 集合从当前 `docs/specs/*/requirements.md` 的 AC 表动态读取，不再硬编码。
  `AC-01~29` 是 M1-P 原型的历史标签，不参与当前门禁。
- **待开工 AC**：`scripts/trace-baseline.txt` 中登记的 AC 没有测试时记 `待开工`，
  不算缺失、不使门禁失败；实现后从基线删除即可转为门禁项。
- **前端 AC**：002 UI 改版的 AC-40~49 是纯前端视觉/交互验收，由 `apps/*/tests`
  与 `scripts/trace.py` 覆盖；后端场景评测不执行浏览器，不要求这些 AC 有 pytest
  场景用例（见 `evals/run.py` 的 `FRONTEND_ONLY_AC`）。
- **多轮场景**：只列覆盖当前 AC 的场景。M1-P 的旧多轮场景测试已随旧 Web 接口删除；
  003 订单查询的多轮场景已重建在 `tests/integration/test_eval_scenarios.py`：
  最近订单 → 单笔 → 转人工 → 坐席接管的订单上下文、跨客户查无不可区分、
  闲聊带“订单”不查询、OMS 连续失败转人工、卡片载荷与审计同链路。
- **前端订单卡片**：AC-58 的字段/白名单由 `tests/integration/test_order_query_AC_58.py`
  断言服务端载荷，渲染与三态由 `apps/chat/tests/OrderCard.test.tsx`、
  `apps/workspace/tests/ConversationOrders.test.tsx` 覆盖。
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

- `evals/reports/latest.json`：每次覆盖；含 AC 状态、测试数、失败测试名、
  待开工 AC、多轮场景耗时。
- `evals/reports/latest.md`：同一份结果的可读版本。
- `evals/reports/<timestamp>.json`：带时间戳的历史报告，失败也写。
- `evals/reports/` 已加入 `.gitignore`，报告由命令再生成。

## 质量基线

- **硬基线**：`latest.json` 的 `ok=true`、`failed=0`、`skipped=0`，且 `ac_coverage.covered + pending = total`；任一不满足，`verify.sh` 失败。
- **Prompt/模型/Tool 变更**：先跑 `./scripts/eval.sh` 并附 `latest.json`/`latest.md` 到执行卡证据，再进入评审；真实模型质量在 M1 只做趋势，不进硬门禁。
- **漂移**：每月对比 `evals/reports/<timestamp>.json` 的 failed/skipped/AC 覆盖；连续两次下降按 [反馈](../docs/process/feedback.md) 环 B 复盘。
- **不伪造基线**：没有真实数据就留 `待补`，不用历史报告代替当前结果。

## 失败条件

以下任一情况 `evals/run.py` 退出 1，并仍写出失败报告：

- 缺少当前 spec 中未登记基线的 AC；
- 当前 spec 找不到可判定的 AC；
- JUnit 中没有测试用例；
- JUnit 无法解析或文件不存在；
- 任一测试失败，或被跳过（跳过不算通过）。

基线中登记的待开工 AC 缺失不算失败，只在报告中标记 `待开工`。
