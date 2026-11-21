# 订单查询任务

> 本文件由 `scripts/gen_tasks.py` 从执行卡 frontmatter 生成，不要手改。
> 新增或调整任务：先改执行卡，再运行 `make gen-tasks`。

- 状态：已批准
- 批准：2026-11-20（用户确认 F-25~F-29 粒度与构建顺序）
- 日期：2026-11-20
- 依据：`requirements.md`、`design.md`
- 构建顺序：F-25 → F-26 → F-27 → F-28 → F-29；一次只做一个，状态由执行卡 frontmatter 决定。
- 切片映射：F-25 ≈ S-01；F-26~F-27 ≈ S-02；F-28 ≈ S-03；F-29 ≈ S-04。
- 状态源：`docs/tasks/003-order-query/F-XX.md` 的 frontmatter

<!-- gen:start -->
| ID | 任务 | AC | 状态 | 卡片 |
|---|---|---|---|---|
| F-25 | 订单访问基座与指定订单查询 | AC-51 | 已完成 | [打开](../../tasks/003-order-query/F-25.md) |
| F-26 | 最近订单、订单意图与澄清 | AC-50、AC-51、AC-52、AC-54 | 已完成 | [打开](../../tasks/003-order-query/F-26.md) |
| F-27 | 订单查询失败分级 | AC-53 | 已完成 | [打开](../../tasks/003-order-query/F-27.md) |
| F-28 | 交接单订单上下文与工作台订单区 | AC-55、AC-56 | 已完成 | [打开](../../tasks/003-order-query/F-28.md) |
| F-29 | 订单卡片、可观测与评测收口 | AC-55、AC-56、AC-57、AC-58 | 已完成 | [打开](../../tasks/003-order-query/F-29.md) |
<!-- gen:end -->
