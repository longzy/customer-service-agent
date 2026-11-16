# evals

场景评测集与报告。

- 覆盖 AC-01 至 AC-21：`evals/run.py` 聚合 pytest JUnit 的 `_AC_XX` 结果，另含 2–3 条多轮编排场景。
- 输出场景级通过率与失败节点。
- 运行：`./scripts/eval.sh`；报告：`evals/reports/latest.json`/`latest.md`。
- 固定、离线、脚本化模型；真实模型质量另列趋势，不进 M1 门禁。
