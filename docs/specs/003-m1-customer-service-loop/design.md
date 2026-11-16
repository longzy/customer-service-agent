# M1 设计：企业客服核心闭环

- 状态：等待评审
- 日期：2026-11-16
- 级别：T3
- 依据：[requirements.md](requirements.md) AC-30~49；[ADR-0005](../../adr/0005-enterprise-boundary.md)；[总体架构](../../architecture/overview.md)
- 说明：本设计覆盖 S2；T3 威胁模型、越权矩阵与回滚预案在第 15–17 节。

## 1. 设计目标与边界

- 客户匿名 Web Chat 与坐席工作台是两个前端、两个入口；后端一个模块化单体。
- 真实身份/RBAC、会话、队列、接管、回复、关闭、审计、持久化；只有 OMS 允许 Mock。
- 复用 R0-2 的 `platform`/`identity`/`domain`/`adapters/oms` 与 `OmsPort`；新增 `conversations` 业务模块。
- M1-P 代码与测试保留为归档资产；新 M1 路由用 `M1_ENABLED` 开关挂载，生产只开 M1。

## 2. 模块与依赖

```text
apps/
  chat/                     # 客户匿名 Web Chat（新）
  workspace/                # 坐席工作台（新）
  web/                      # M1-P 归档，不再作为 M1 入口
services/
  api/
    customer_routes.py      # /customer/*
    workspace_routes.py     # /workspace/*
    legacy/                 # 现有 M1-P 路由，测试环境保留
  conversations/            # 会话、消息、交接单、队列、领取/接管
  identity/                 # 员工账号、密码、session、RBAC；匿名客户 session
  platform/                 # db/models/settings/observability/outbox/worker/ratelimit/retention
  domain/                   # orders/cancellation/errors
  tools/                    # ToolGateway + query/cancel/policy
  workflows/                # 取消 Workflow
  adapters/oms/             # OmsPort + Mock/Http + factory
packages/contracts/         # HTTP/OpenAPI 与前端类型
```

依赖规则：

- `api` → `conversations`/`identity`/`platform`/`tools`/`workflows`/`adapters.oms.port`。
- `conversations` → `platform`/`identity`/`domain`/`tools`/`workflows`/`adapters.oms.port`；不得 import `api`。
- `tools`/`workflows` → `domain`/`identity`/`platform`/`adapters.oms.port`；不得 import `conversations`/`api`/具体 Adapter。
- `identity` → `platform`；不 import `conversations`/`tools`/`workflows`。
- `platform` → 标准库/第三方；不 import 业务模块。
- `apps/*` 只经 HTTP + `packages/contracts`；客户 app 不含员工认证；工作台 app 不依赖客户 cookie。

## 3. 数据模型与迁移

M1 复用现有会话/消息/交接单/取消/审计表，追加可空列；新增身份、订单授权、限速与 outbox 表。迁移全部为**加法**，`user_id` 改为可空以支持匿名客户；不删除 M1-P 数据。

| 表 | 变更 | 关键列/约束 |
|---|---|---|
| `conversations` | 加列、`user_id` 可空 | `customer_session_id?`、`status`、`assigned_agent_id?`、`journey_id?` |
| `messages` | 加列 | `author_type?`（customer/ai/agent/system）；保留 `role` 兼容旧数据 |
| `handoffs` | 加列、`user_id` 可空 | `customer_session_id?`、`status`、`reason`、`priority`、`claimed_by?`、`claimed_at?`、`version`、`verified_order_ids` JSON、`journey_id?` |
| `cancellation_requests` | 加列、`user_id` 可空 | `customer_session_id?`；幂等唯一键仍 `(tenant_id, idempotency_key)` |
| `audit_events` | 加列 | `journey_id?`；保留 actor/event 字段 |
| `customer_sessions` | 新表 | id、tenant_id、nickname?、token_hash、created_at、expires_at、revoked_at、last_seen_at |
| `employees` | 新表 | id、tenant_id、username、password_hash（scrypt）、role、display_name、active；唯一 `(tenant_id, username)` |
| `employee_sessions` | 新表 | id、employee_id、token_hash、created_at、expires_at、revoked_at、last_seen_at |
| `order_access_grants` | 新表 | id、customer_session_id、tenant_id、order_id、verified_at、expires_at；唯一 `(customer_session_id, order_id)` |
| `rate_limit_buckets` | 新表 | `(bucket_key, window_start)` 主键、count；原子 upsert |
| `outbox_events` | 新表 | id、event_type、aggregate_type/id、payload、status、attempts、available_at、created_at、processed_at |

索引：`conversations(customer_session_id)`、`conversations(status)`、`handoffs(status, created_at)`、`handoffs(claimed_by)`、`messages(conversation_id, created_at)`、`audit_events(journey_id, created_at)`、`order_access_grants(expires_at)`。

迁移顺序：新表 → 可空列/索引 → 回填旧行（`status` 等保持 NULL，旧路由忽略）→ 不删除旧列。

## 4. 状态机

### 4.1 会话

| From | 动作 | To | 执行者 |
|---|---|---|---|
| `AI_ACTIVE` | 转人工 | `QUEUED` | 客户/策略 |
| `AI_ACTIVE` | 客户结束 | `CLOSED` | 客户 |
| `QUEUED` | 领取 | `CLAIMED` | 坐席 |
| `QUEUED` | 客户结束 | `CLOSED` | 客户 |
| `CLAIMED` | 接管 | `HUMAN_ACTIVE` | 领取坐席 |
| `CLAIMED` | 关闭 | `CLOSED` | 领取坐席 |
| `HUMAN_ACTIVE` | 关闭 | `CLOSED` | 接管坐席 |
| `HUMAN_ACTIVE` | 转回 AI | `AI_ACTIVE` | 接管坐席 |
| `CLOSED` | 任意写 | 拒绝 409 | — |

### 4.2 交接单

`QUEUED → CLAIMED → ACTIVE → CLOSED`；与会话状态在同一事务更新。`CLOSED` 后队列不再返回。

### 4.3 员工 session

`ACTIVE → EXPIRED/REVOKED`；8h 绝对过期；登出立即 `REVOKED`。

### 4.4 取消任务

沿用 001 状态机（`COLLECTING`…`ABANDONED`）；客户确认权与幂等不变。

## 5. 匿名会话与订单访问

- `POST /customer/sessions`：无 cookie 时创建 256-bit token；存 SHA-256；cookie `csid`（HttpOnly、SameSite=Lax、生产 Secure）；24h 绝对过期。
- 无效/过期 cookie → 401 `SESSION_INVALID`/`SESSION_EXPIRED`；只有显式 `POST /customer/sessions` 才新建，不自动合并旧会话。
- `POST /customer/orders/verify`：`order_id` + `phone_last4`（4 位数字）；格式 422；限速；调用 `OmsPort.verify_order_access(tenant_id, order_id, phone_last4)`。
- 成功写 `order_access_grants`（到期=会话到期）；失败 403 `ORDER_VERIFICATION_FAILED`，统一文案；不存手机号。
- 查询/取消使用 `OmsAccess(tenant_id, user_id=None, verified_order_ids=...)`；只允许会话内已授权订单。
- 客户跨会话/跨租户读取 → 404；`order_access_grants` 按 session 隔离。

`OmsPort` 扩展：

```python
def verify_order_access(self, tenant_id: str, order_id: str, phone_last4: str) -> bool: ...
```

Mock 夹具增加 `phone_last4`（测试数据，不是真实 PII）；Http 映射 `POST /orders/{id}/access-verifications`。

## 6. 员工身份、RBAC 与 session

- `employees` 由种子脚本创建；M1 只有 `role="agent"`；无账号管理界面。
- 密码：`hashlib.scrypt`（N=2^14, r=8, p=1，16-byte salt）；格式 `scrypt$n$r$p$salt$hash`；常数时间比较。
- `POST /workspace/sessions`：用户名+密码；失败统一 401 `AUTH_FAILED`；5 次/15min/账号+IP → 429。
- 员工 session：256-bit token、SHA-256 存储、8h 绝对过期、登录轮换、登出立即撤销；cookie `esid` 同上属性。
- `current_employee` 依赖：解析 cookie、校验角色/租户；未登录 401，非 agent 403。
- 跨租户/他人会话 404。

## 7. 队列、领取与接管

- 队列查询：`status='QUEUED'`，`ORDER BY created_at, id`；返回 handoff_id、等待秒数、原因、订单数、脱敏末条（≤100 字）。
- 领取：`UPDATE handoffs SET status='CLAIMED', claimed_by=:me, claimed_at=now(), version=version+1 WHERE id=:id AND status='QUEUED' AND version=:v RETURNING ...`；无行 → 409 `CLAIM_CONFLICT`。
- 领取资格：`agent` + 同租户 + `QUEUED` + 未被领取；M1 无自动分配、无并发上限。
- 接管：`UPDATE ... WHERE id=:id AND claimed_by=:me AND status='CLAIMED'`；设 `HUMAN_ACTIVE`、`ACTIVE`，写系统消息“人工已接入”，审计 + outbox；无行 → 404。
- 非领取者查看/接管 → 404；领取冲突 409。

## 8. 转人工与交接单

- 触发由确定性 `HandoffPolicy` + 模型输出：显式转人工接口/意图、`MANUAL_REVIEW`、同一取消任务 OMS 连续 2 次 Timeout/Connection、`SUBMIT_UNKNOWN`、模型 10s 超时、置信度 <0.6；优先级按 requirements 6.1。
- 交接单创建与会话 `AI_ACTIVE→QUEUED` 同事务；写 `summary`（≤500 字）、`context`（最近 20 条且≤4000 字）、`verified_order_ids`、`pending_step`、`reason`、`priority`、`journey_id`。
- 摘要可由模型生成，但字段/裁剪/脱敏由服务端补齐；脱敏清单按 requirements 6.8。
- 无坐席领取时 `QUEUED` 持久化；客户轮询看到等待；不依赖 presence。

## 9. AI Runtime 与 Tool 上下文

- `AgentRuntime.reply(context)` 返回 `{reply, confidence, tool_calls, handoff_reason?}`；模型超时 10s；失败转 `MODEL_UNAVAILABLE`。
- 模型只能建议 Tool；实际调用经 `ToolGateway`，Schema/白名单/授权/审计不变。
- `ToolContext`：

```python
@dataclass(frozen=True)
class ToolContext:
    tenant_id: str
    actor_type: Literal["customer", "agent"]
    actor_id: str
    oms_access: OmsAccess
```

- `ToolGateway.invoke(name, payload, context)`；handlers 用 `context.oms_access`；审计记录 actor。旧 M1-P 路径用 `Identity` 适配为 `ToolContext`，保持 001 测试。
- 客户 `oms_access` 来自会话 grants；坐席来自交接单 `verified_order_ids`，不把坐席当订单归属用户。
- 低置信/高风险仍由确定性 `HandoffPolicy` 决定；模型只给 confidence/intent。

## 10. HTTP 契约

### 客户（cookie `csid`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/customer/sessions` | 新建/显式新会话；返回昵称、状态 |
| GET | `/customer/session` | 当前会话状态 |
| POST | `/customer/messages` | 发消息；返回 AI 回复或排队状态 |
| GET | `/customer/messages?since=` | 轮询消息 |
| POST | `/customer/orders/verify` | 订单号 + 尾号 |
| GET | `/customer/orders` | 已校验订单摘要 |
| POST | `/customer/orders/{id}/cancellations` | 请求取消/确认 |
| POST | `/customer/handoff` | 显式转人工 |
| POST | `/customer/session/close` | 客户结束 |

### 坐席（cookie `esid`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/workspace/sessions` | 登录 |
| DELETE | `/workspace/sessions` | 登出 |
| GET | `/workspace/queue` | 队列摘要 |
| POST | `/workspace/queue/{handoff_id}/claim` | 条件领取 |
| POST | `/workspace/conversations/{id}/takeover` | 接管 |
| GET | `/workspace/conversations/{id}` | 上下文（消息/订单/AI 轨迹/交接单/待办） |
| GET | `/workspace/conversations/{id}/messages?since=` | 轮询 |
| POST | `/workspace/conversations/{id}/messages` | 回复 |
| POST | `/workspace/conversations/{id}/cancellations` | 请求客户确认 |
| POST | `/workspace/conversations/{id}/close` | 关闭 |
| POST | `/workspace/conversations/{id}/return-to-ai` | 转回 AI |

错误封套沿用 `code/retryable/visible/message`；新增 `SESSION_INVALID`、`SESSION_EXPIRED`、`AUTH_FAILED`、`ORDER_VERIFICATION_REQUIRED`、`ORDER_VERIFICATION_FAILED`、`CLAIM_CONFLICT`、`RATE_LIMITED`、`CONVERSATION_CLOSED`。

## 11. 前端

- `apps/chat`：昵称/进入、消息流、订单校验、确认卡片、订单摘要、转人工/排队状态；3s 轮询；无员工认证代码。
- `apps/workspace`：登录、队列、会话列表、消息、订单必要字段、AI 轨迹、交接单/待办、回复、请求取消、关闭/转回。
- 两个 Next.js app，共用 `packages/contracts` 类型；不共用页面/路由；`apps/web` 保留为 M1-P 归档，不链接到 M1。
- 前端只做展示与交互；所有授权/状态转换在服务端。

## 12. 审计、Trace、outbox、worker 与保留

- `audit_events` 记录 actor_type/actor_id、event_type、entity、result_status、journey_id、trace_id、脱敏 metadata；写失败变更操作 503，不提交。
- 事件：`session.created`、`order.verified`、`handoff.created`、`handoff.claimed`、`conversation.taken_over`、`message.replied`、`cancellation.requested/confirmed/rejected`、`conversation.closed`、`conversation.returned_to_ai`、`auth.login/failed/logout`。
- outbox：交接单/领取/接管/关闭等事件写 outbox，由 worker 投递（M1 只做持久化与 at-least-once；消费端幂等）。
- worker：`python -m services.platform.worker`；轮询 outbox + 保留清理 + 限速桶清理；异常告警，不阻塞 API。
- 保留：session 24h；messages/handoffs 30d 硬删除；audit 90d 归档/删除；rate buckets 过期清理；完整手机号从不落库。

## 13. 限速

- PostgreSQL `rate_limit_buckets` 原子 upsert（`INSERT ... ON CONFLICT DO UPDATE count=count+1 RETURNING count`）。
- key：`msg:{session}`、`verify:{session}`、`verify_ip:{ip}`、`login:{username}:{ip}`。
- 窗口：1min/10min/1h/15min；超限 429 `RATE_LIMITED`；无副作用；登录存在/不存在账号一致。
- 单实例 PostgreSQL 实现；多实例仍共享 DB，不依赖进程内存。

## 14. 错误映射

| 场景 | 状态码/错误 |
|---|---|
| 未登录/会话无效 | 401 `SESSION_INVALID`/`SESSION_EXPIRED` |
| 非 agent | 403 `FORBIDDEN` |
| 跨租户/他人会话 | 404 `NOT_FOUND` |
| 未校验订单查询 | 403 `ORDER_VERIFICATION_REQUIRED` |
| 校验失败 | 403 `ORDER_VERIFICATION_FAILED` |
| 领取冲突 | 409 `CLAIM_CONFLICT` |
| 关闭后写 | 409 `CONVERSATION_CLOSED` |
| 参数非法 | 422 |
| 超限 | 429 `RATE_LIMITED` |
| 审计失败 | 503 `AUDIT_UNAVAILABLE` |

客户/坐席文案由前端按 code 映射；不返回内部堆栈/存在性细节。

## 15. T3 威胁模型

| 威胁 | 向量 | 控制 | 验证 | 残余风险 |
|---|---|---|---|---|
| 会话伪造/固定 | 猜测/注入 csid | 256-bit 随机、哈希存储、HttpOnly/Secure/SameSite、轮换、24h 过期 | AC-30/49 | 设备被控 |
| 跨会话/跨租户越权 | 改 id/cookie | 服务端 session 绑定、404、租户校验 | AC-33/49 | 内部误配 |
| 订单枚举 | 遍历订单号/尾号 | 统一失败、限速、不区分存在性 | AC-32/47 | 低频枚举 |
| 队列抢占/双坐席 | 并发领取/接管 | 条件更新、版本、唯一归属、409/404 | AC-39/40 | DB 故障 |
| 坐席越权 | 改 URL/角色 | RBAC、归属校验、404 | AC-38/41 | 账号共享 |
| 取消越权/代确认 | 坐席直接提交 | 客户会话内确认、Workflow、幂等 | AC-42 | 客户被社工 |
| 审计篡改 | 改库/接口 | 只读 API、无删除、服务端写、DB 权限 | AC-45 | DBA |
| PII 泄露 | 日志/交接单/工作台 | 不存完整手机号、脱敏清单、最小字段 | AC-36/45/46 | 用户输入 |
| DoS/刷接口 | 高频消息/登录/校验 | PostgreSQL 限速桶、body/消息长度上限 | AC-47 | 分布式 IP |
| Prompt 注入/工具滥用 | 恶意消息 | Tool 白名单/Schema/确定性 Policy/无 DB 直连 | AC-31/45 | 模型误判 |
| 重放/重复取消 | 重发请求 | 幂等键、唯一约束、状态机 | AC-34/42 | 客户端重试 |

## 16. 越权矩阵

| 资源/动作 | 匿名客户 | 未登录 | agent（同租户） | agent（他租户） | 非 agent |
|---|---|---|---|---|---|
| 自己的会话/消息 | 允许 | 401 | 仅接管/可领取 | 404 | 403 |
| 他人会话/消息 | 404 | 401 | 404 | 404 | 403 |
| 已校验订单 | 允许 | 401 | 交接单集合内允许 | 404 | 403 |
| 未校验订单 | 403 要求校验 | 401 | 404 | 404 | 403 |
| 队列摘要 | 403 | 401 | 允许 | 空/404 | 403 |
| 领取/接管 | 403 | 401 | 条件允许 | 404 | 403 |
| 审计 | 禁止 | 401 | 只读本人会话 | 404 | 403 |

## 17. 回滚与发布

- 特性开关 `M1_ENABLED`：关闭时不挂载 `/customer/*`、`/workspace/*` 与 worker；旧 M1-P 路由仍可用。
- 迁移全部加法；回滚代码不删表/列，避免数据丢失。
- 回滚步骤：关 `M1_ENABLED` → 回滚部署 → 观察旧路径；如需降级 schema，先备份并只删 M1 新表/列（需人工批准）。
- 演练：在临时库对 M1 迁移执行 upgrade→downgrade 的可用性检查；生产回滚以开关为主。
- 观测：新路由 5xx、领取冲突、审计失败、限速命中、队列积压。

## 18. 测试与评测 seam

| seam | 测试 |
|---|---|
| 客户会话/订单校验 | HTTP 路由 + session/grant 仓储 + Cookie 属性 |
| AI 回复/模型失败 | `FakeModelClient` 注入 + 消息仓储 + 交接单 |
| 队列/领取/接管 | 条件更新并发测试 + 状态机 |
| 员工登录/RBAC | 身份服务 + 工作台路由 + 越权矩阵 |
| 审计/Trace | 审计表 + journey/trace + 失败注入 |
| 限速 | 限速器 + 可注入阈值 + 429 |
| 保留清理 | worker + 可注入时钟 + DB/日志 |
| 前端 | chat/workspace 组件测试 + 轮询/失败路径 |
| 端到端 | 6.9 场景评测；FakeModel；独立测试库 |

## 19. 开放项

- 队列位置/SLA 展示、客户等待文案。
- 员工密码策略、种子账号数量/租户。
- 模型成本/延迟目标与真实模型评测排期。
- 审计归档介质、清理任务频率。
