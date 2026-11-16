# A 切片需求：客户 ↔ AI ↔ 人工转接闭环

- 状态：已批准
- 批准：2026-11-17（用户确认 A 共同理解；重置后使用 AC-30~AC-39）
- 日期：2026-11-17
- 级别：T3（客户/员工认证、会话归属、队列权限、审计）
- 依据：[产品宪章](../../product/charter.md)、[ADR-0006](../../adr/0006-customer-login.md)、[总体架构](../../architecture/overview.md)
- 范围：客户登录/会话、AI 对话、消息触发转人工、坐席登录/队列/领取/接管/回复/关闭/转回、A/B 对等、审计/限速
- 不范围：订单（B，004）、取消（C，005）、保留清理/全量评测（D，006）、客户自助注册/OTP、主管/管理员、自动分配、真实 OMS、WebSocket
- 垂直票：T-29 客户登录+聊天+转人工 → T-30 坐席登录+队列+领取+接管 → T-31 回复/关闭/转回+端到端

## 1. 目标

A 是 M1 的第一条垂直切片，端到端可演示：

```text
客户 A 登录 -> 发消息 -> AI 回复
  -> 发“转人工”消息（无按钮）
  -> 交接单入队，客户看到排队
坐席 1 登录 -> 队列领取 A -> 接管
  -> 客户看到“人工已接入”
  -> 坐席回复 -> 关闭 / 转回 AI

客户 B 登录 -> 独立会话 -> 同样可聊天、转人工、被接管、回复、关闭、转回
```

A/B 能力完全一致；不做客户分级。

## 2. 非目标

- 订单列表/详情、AI 查单 Tool（B）。
- 取消/确认/30min/幂等（C）。
- 历史会话列表；客户注册/找回密码/OTP/MFA；主管/管理员。
- 自动分配；真实 OMS；WebSocket/SSE；30d/90d 保留清理；全量评测矩阵（D）。

## 3. 验收标准

| AC | 场景 | 期望 |
|---|---|---|
| AC-30 | 客户登录/刷新/重新登录/登出；错误密码；过期 session | 预置账号/密码；24h 绝对 session；登录轮换 token；Cookie `HttpOnly/SameSite=Lax/Secure(prod)`；一个客户一个未关闭会话；登录恢复；未超限错误/登出/过期 401，超限 429；跨客户 404 |
| AC-31 | 客户发普通消息；模型超时/不可用 | 消息持久化；10s 内 AI 回复；模型失败自动转人工；不接订单 Tool |
| AC-32 | 客户发“转人工/人工客服/真人”或自然表达；低置信（默认 0.6）；问订单/超范围 | 无按钮；关键词优先 + 模型 intent；命中/低置信/超范围/模型失败都创建交接单入队；交接单含客户账号、摘要≤500 字、最近 20 条且≤4000 字消息、AI 轨迹、原因、待办、脱敏，`order_count=0`；客户看到排队 |
| AC-33 | A/B 两客户完整操作；A 读 B 会话 | A/B 都能登录、聊天、转人工、被接管、回复、关闭、转回；A 读 B 会话/消息 404；各自独立交接单 |
| AC-34 | 员工登录/错误密码/8h 过期/登出/非 agent | 2 个坐席种子账号；8h 绝对 session；登录轮换撤销旧 session；未超限错误/登出/过期 401，超限 429；非 agent 403；跨租户/他人会话 404 |
| AC-35 | 多个 QUEUED；并发领取；跨租户；已领取 | FIFO；摘要含客户账号/等待/原因/脱敏末条/`order_count=0`；条件领取；并发仅一个成功，另一个 409；跨租户/越权 404；无自动分配 |
| AC-36 | QUEUED 摘要；领取后接管；查看上下文；第二坐席查看/接管 | QUEUED 只看到客户账号/等待/原因/订单数 0/脱敏末条；领取者接管，`CLAIMED→HUMAN_ACTIVE`；客户收到“人工已接入”；本人看到客户账号、消息、AI 轨迹、交接单、待办；第二坐席领取 409、查看/接管 404 |
| AC-37 | 坐席回复；客户轮询；人工中客户发消息 | 回复持久化，客户 3s 轮询可见；人工中客户消息不再触发 AI；消息不丢 |
| AC-38 | 客户任意状态关闭；关闭后再发；坐席关闭/转回；转回后再次转人工 | 客户可关闭任意未关闭会话，交接单/队列同事务关闭；关闭后客户再发 409；坐席可关闭/转回；转回后同一会话 AI 恢复历史；再次转人工生成新交接单；同一会话不出现两张 open 单 |
| AC-39 | 登录/转人工/领取/接管/回复/关闭/转回；限速；审计失败；坐席改删审计；401/403/429 | 关键动作有审计；审计不可改删；401/403/429 安全事件审计；客户/员工登录与客户消息限速；审计失败变更 503；A/B 越权 404 |

## 4. 页面与 API

**客户 app `apps/chat`**

- `/login`：预置账号/密码；不做“选择测试账号”。
- `/chat`：消息流、输入框、排队/人工状态、关闭会话、登出；**无转人工按钮**；无订单/取消。

**坐席 app `apps/workspace`**

- `/login`。
- `/queue`：队列列表、领取。
- `/conversations/[id]`：客户账号、消息、AI 轨迹、交接单摘要、回复、关闭、转回 AI；无订单/取消面板。

**API**

- 客户：`POST /customer/sessions`、`DELETE /customer/sessions`、`GET /customer/session`、`POST /customer/messages`、`GET /customer/messages?after_id=`、`POST /customer/session/close`。
- 坐席：`POST /workspace/sessions`、`DELETE /workspace/sessions`、`GET /workspace/queue`、`POST /workspace/queue/{handoff_id}/claim`、`POST /workspace/conversations/{id}/takeover`、`GET /workspace/conversations/{id}`、`GET /workspace/conversations/{id}/messages?after_id=`、`POST /workspace/conversations/{id}/messages`、`POST /workspace/conversations/{id}/close`、`POST /workspace/conversations/{id}/return-to-ai`。
- 不提供 `/customer/handoff`（消息触发）、订单、取消接口。

## 5. 错误码、轮询、AI 轨迹、队列摘要

- 错误码：401 `SESSION_INVALID`/`SESSION_EXPIRED`/`AUTH_FAILED`；403 `FORBIDDEN`；404 `NOT_FOUND`；409 `CLAIM_CONFLICT`/`CONVERSATION_CLOSED`；422 `VALIDATION_ERROR`；429 `RATE_LIMITED`；503 `AUDIT_UNAVAILABLE`。
- 轮询：客户/坐席每 3s 拉 `messages?after_id=` 与状态；`after_id` 为消息 ID；无 WebSocket/SSE。
- AI 轨迹：最近 20 条模型/Tool 事件，含 `event_type`、`name`、`status`、`confidence?`、`trace_id`；不存/不返 prompt/response 正文与 PII；A 无订单 Tool。
- 队列摘要：`handoff_id`、`conversation_id`、客户账号/显示名、等待秒数、原因、`order_count=0`、脱敏末条（≤100 字）；领取前不返回完整消息。
- 交接单摘要：客户身份、摘要≤500 字、最近 20 条且≤4000 字消息、AI 轨迹、原因、待办、`order_count=0`；订单集合为空。

## 6. 垂直票与 blocking edges

| 票 | 内容 | AC | 演示路径 | blocked by |
|---|---|---|---|---|
| T-29 | 客户登录 + 聊天 + AI + 转人工 | AC-30、AC-31、AC-32 | 客户登录→聊天→发“转人工”→看到排队 | — |
| T-30 | 坐席登录 + 队列 + 领取 + 接管 | AC-34、AC-35、AC-36 | 坐席登录→队列→领取→接管→客户看到“人工已接入” | T-29 |
| T-31 | 回复 + 关闭/转回 + A/B 端到端 + 审计/限速 | AC-33、AC-37、AC-38、AC-39 | A/B 都完整走通；审计/限速收口 | T-30 |

安全/审计/限速折进每张票，不单开“安全票”。

## 7. 验收方式

- 10 条 AC 自动化：pytest/API + FakeModel，2 客户/2 坐席。
- 人工走查：A/B 两个客户在两个 app 完整走一遍，录一次证据。
- 不做全量评测矩阵（D）。

## 8. 数据与认证

- 新 `service_*` 表：客户/员工账号、session、会话、消息、交接单、AI 事件、审计、限速；旧 M1-P 表/路由不动。
- 真实客户/员工登录/session/RBAC；2 客户/2 坐席种子账号；A 不接 OMS。
- 客户 24h、员工 8h；一个客户一个未关闭会话；跨客户/跨租户 404。

## 9. 证据 seam

| 事实 | seam |
|---|---|
| 客户登录/session/恢复 | 客户认证路由 + `service_customers`/`service_customer_sessions` + Cookie 测试 |
| AI 回复/模型失败 | `FakeModelClient` + `service_messages` + 交接单 |
| 转人工意图 | 关键词 + 模型 intent + `service_handoffs` |
| 员工登录/RBAC | 身份服务 + 工作台路由 + 越权测试 |
| 队列/领取/接管 | 条件更新 + 并发测试 + 状态机 |
| 回复/关闭/转回 | 消息/状态机 + 客户轮询 |
| 审计/限速 | `service_audit_events` + `service_rate_limit_buckets` |
| 前端 | `apps/chat`/`apps/workspace` 组件/轮询/失败路径 |

## 10. S2 待定

- 客户/员工 session 表与密码哈希细节。
- 关键词列表、模型 intent 输出 schema；低置信阈值默认 0.6，可配置。
- 队列/接管 SQL 与事务边界。
- AI 轨迹事件字段、交接单摘要裁剪。
- 两个 app 的脚手架与轮询实现。
