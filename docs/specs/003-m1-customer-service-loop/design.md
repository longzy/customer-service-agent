# M1 设计：企业客服核心闭环

- 状态：草案
- 日期：2026-11-16
- 说明：S1.5 通过 requirements 后进入 S2。本文件当前为占位，用于保持 spec 结构完整；S2 将补齐以下内容。

## S2 必须覆盖

1. 模块边界：`api`/`conversations`/`identity`/`queue`/`tools`/`workflows`/`adapters/oms` 的依赖与事务归属。
2. 状态机：会话、交接单、队列、员工 session、取消任务；合法迁移表与并发冲突。
3. 数据模型与迁移：匿名会话、消息、交接单、队列/领取、员工账号/session、审计。
4. HTTP/JSON 契约：客户聊天、订单校验、队列、领取、接管、回复、关闭、转回 AI。
5. 身份/RBAC：密码哈希、session 轮换、角色校验、登录限速。
6. 匿名会话与订单访问：token、24h 过期、订单校验、verified_order_ids、隐私最小化。
7. 队列领取：FIFO、条件更新/版本、并发唯一坐席、无坐席排队。
8. 转人工：触发优先级、交接单内容、摘要生成与脱敏。
9. 工作台：队列/会话/订单/AI 轨迹/交接单/待办；客户聊天与工作台两个前端。
10. 审计/Trace/outbox/worker；关键动作与 `trace_id`。
11. 保留清理 worker：24h/30d/90d；完整手机号不落库/日志。
12. 错误映射、限速、失败文案；客户与坐席可见状态。
13. T3 威胁模型、越权矩阵、回滚预案。
14. 测试 seam、场景评测与岗位走查方案。

## 设计前置

- requirements AC-30~48 已通过 S1.5。
- 复用 `002` 的 `platform`/`identity`/`domain`/`adapters/oms` 与 `OmsPort`。
- 不改 R0-2 的边界规则；新模块按 `conversations`/`queue` 增量加入。
