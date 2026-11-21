# 客户转人工闭环任务

> 本文件由 `scripts/gen_tasks.py` 从执行卡 frontmatter 生成，不要手改。
> 新增或调整任务：先改执行卡，再运行 `make gen-tasks`。

- 状态：已批准
- 批准：2026-11-17（用户确认 14 条 feature 粒度）
- 日期：2026-11-17
- 依据：`requirements.md`、`design.md`
- 构建顺序：F-01 → F-02 → … → F-14；一次只做一个，状态由执行卡 frontmatter 决定。
- 切片映射：F-01~F-04 ≈ S-01；F-05~F-09 ≈ S-02；F-10~F-14 ≈ S-03。
- 状态源：`docs/tasks/001-customer-handoff/F-XX.md` 的 frontmatter

<!-- gen:start -->
| ID | 任务 | AC | 状态 | 卡片 |
|---|---|---|---|---|
| F-01 | 客户登录、会话恢复与登出 | AC-30 | 已完成 | [打开](../../tasks/001-customer-handoff/F-01.md) |
| F-02 | 客户消息与 AI 回复 | AC-31 | 已完成 | [打开](../../tasks/001-customer-handoff/F-02.md) |
| F-03 | 关键词转人工与完整交接单 | AC-32 | 已完成 | [打开](../../tasks/001-customer-handoff/F-03.md) |
| F-04 | 低置信/问订单/超范围转人工 | AC-32 | 已完成 | [打开](../../tasks/001-customer-handoff/F-04.md) |
| F-05 | 坐席登录与 RBAC | AC-34 | 已完成 | [打开](../../tasks/001-customer-handoff/F-05.md) |
| F-06 | 工作台队列 FIFO 与摘要 | AC-35 | 已完成 | [打开](../../tasks/001-customer-handoff/F-06.md) |
| F-07 | 队列条件领取（并发只成功一人） | AC-35 | 已完成 | [打开](../../tasks/001-customer-handoff/F-07.md) |
| F-08 | 领取后接管与完整上下文 | AC-36 | 已完成 | [打开](../../tasks/001-customer-handoff/F-08.md) |
| F-09 | 第二坐席查看/接管越权矩阵 | AC-36 | 已完成 | [打开](../../tasks/001-customer-handoff/F-09.md) |
| F-10 | 坐席回复与实时消息轮询 | AC-37 | 已完成 | [打开](../../tasks/001-customer-handoff/F-10.md) |
| F-11 | 客户关闭会话 | AC-38 | 已完成 | [打开](../../tasks/001-customer-handoff/F-11.md) |
| F-12 | 坐席关闭会话与转回 AI | AC-38 | 已完成 | [打开](../../tasks/001-customer-handoff/F-12.md) |
| F-13 | 审计、限速与审计失败回滚 | AC-39 | 已完成 | [打开](../../tasks/001-customer-handoff/F-13.md) |
| F-14 | 客户甲/乙端到端闭环与跨客户隔离 | AC-33 | 已完成 | [打开](../../tasks/001-customer-handoff/F-14.md) |
| F-24 | 模型失败分级降级 | AC-31、AC-32 | 已完成 | [打开](../../tasks/001-customer-handoff/F-24.md) |
<!-- gen:end -->
