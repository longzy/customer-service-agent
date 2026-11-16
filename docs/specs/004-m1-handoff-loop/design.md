# A 设计：客户 ↔ AI ↔ 人工转接闭环

- 状态：草案
- 依据：[requirements](requirements.md)、[003 契约](../003-m1-customer-service-loop/design.md)
- 说明：S1.5 通过后进入 S2；本文件当前为占位。

## S2 必须覆盖

1. `service_customers`/`service_customer_sessions`/`service_employees`/`service_employee_sessions` 表与认证。
2. `service_conversations`/`service_messages`/`service_handoffs` 状态机与一个客户一个未关闭会话约束。
3. 客户/员工 API、Cookie、CSRF/Origin、错误码。
4. 关键词 + 模型 intent 的转人工策略、低置信阈值、模型失败。
5. 队列 FIFO/条件领取/接管并发，handoff+conversation+audit/outbox 同事务。
6. 坐席回复、客户轮询、关闭/转回、系统消息。
7. AI 轨迹事件与队列/交接单摘要字段、脱敏。
8. 审计/限速/越权矩阵、T3 威胁模型、测试 seam。
9. `apps/chat`/`apps/workspace` 两个 Next app 的最小页面。

## 不做

订单（B）、取消（C）、保留清理/全量评测（D）。
