# UI 改版任务

> 本文件由 `scripts/gen_tasks.py` 从执行卡 frontmatter 生成，不要手改。
> 新增或调整任务：先改执行卡，再运行 `make gen-tasks`。

- 状态：已批准
- 批准：2026-11-18（用户确认 AC-40~AC-49；一次上线，按 feature 逐条提交）
- 日期：2026-11-18
- 依据：`requirements.md`、`design.md`
- 构建顺序：F-15 → F-16 → … → F-23；一次只做一个，状态由执行卡 frontmatter 决定。
- 切片映射：F-15 ≈ S-01；F-16~F-17 ≈ S-02；F-18~F-22 ≈ S-03；F-23 ≈ S-04。
- 状态源：`docs/tasks/002-ui-redesign/F-XX.md` 的 frontmatter

<!-- gen:start -->
| ID | 任务 | AC | 状态 | 卡片 |
|---|---|---|---|---|
| F-15 | S1 令牌接入 | AC-40 | 已完成 | [打开](../../tasks/002-ui-redesign/F-15.md) |
| F-16 | 客户登录页 | AC-41 | 已完成 | [打开](../../tasks/002-ui-redesign/F-16.md) |
| F-17 | 客户聊天页 | AC-42 | 已完成 | [打开](../../tasks/002-ui-redesign/F-17.md) |
| F-18 | 坐席登录页 | AC-43 | 已完成 | [打开](../../tasks/002-ui-redesign/F-18.md) |
| F-19 | 坐席队列 | AC-44 | 已完成 | [打开](../../tasks/002-ui-redesign/F-19.md) |
| F-20 | 右栏摘要详情 | AC-45 | 已完成 | [打开](../../tasks/002-ui-redesign/F-20.md) |
| F-21 | 队列四态 | AC-46 | 已完成 | [打开](../../tasks/002-ui-redesign/F-21.md) |
| F-22 | 可访问性与响应式收口 | AC-47、AC-48 | 已完成 | [打开](../../tasks/002-ui-redesign/F-22.md) |
| F-23 | 视觉回归与规范收口 | AC-49 | 已完成 | [打开](../../tasks/002-ui-redesign/F-23.md) |
<!-- gen:end -->
