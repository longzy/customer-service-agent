# 订单取消任务

> 本文件由执行卡 frontmatter 生成，不要手改；当前为已批准任务索引。
> 新增或调整任务：先按 `docs/templates/task-design-card.md` 写 `docs/tasks/004-order-cancel/F-XX.md`（DoR §2.1、seam §2.3、判定表 §2.5、发布/回滚 §7），再运行 `make gen-tasks`。

- 状态：已批准
- 批准：2026-11-21（用户确认 F-30~F-36 粒度与构建顺序）
- 日期：2026-11-21
- 模板：`docs/templates/task-design-card.md`（2026-11-21）
- 依据：`requirements.md`、`design.md`
- 构建顺序：F-30 → F-31 → F-32 → F-33 → F-34 → F-35 → F-36；一次一个。
- 切片映射：F-30 ≈ S-01；F-31 ≈ S-02；F-32 ≈ S-03；F-33 ≈ S-04；F-34 ≈ S-05；F-35 ≈ S-06；F-36 ≈ S-06/S-07。
- 状态源：`docs/tasks/004-order-cancel/F-XX.md`

## 任务索引

<!-- gen:start -->
| ID | 任务 | AC | 状态 | 卡片 |
|---|---|---|---|---|
| F-30 | 我的订单独立页面与列表查询 | AC-59 | 已完成 | [打开](../../tasks/004-order-cancel/F-30.md) |
| F-31 | 列表取消按钮与客户确认 | AC-60、AC-61、AC-62 | 已完成 | [打开](../../tasks/004-order-cancel/F-31.md) |
| F-32 | 聊天入口与订单号兜底 | AC-63、AC-61 | 已完成 | [打开](../../tasks/004-order-cancel/F-32.md) |
| F-33 | 资格、越权与幂等 | AC-64、AC-65、AC-66 | 已完成 | [打开](../../tasks/004-order-cancel/F-33.md) |
| F-34 | 提交恢复与可观测 | AC-67、AC-70 | 待评审 | [打开](../../tasks/004-order-cancel/F-34.md) |
| F-35 | 异常转人工与交接单 | AC-68 | 未开始 | [打开](../../tasks/004-order-cancel/F-35.md) |
| F-36 | 坐席发起、工作台取消区与评测收口 | AC-69、AC-71、AC-72 | 未开始 | [打开](../../tasks/004-order-cancel/F-36.md) |
<!-- gen:end -->
