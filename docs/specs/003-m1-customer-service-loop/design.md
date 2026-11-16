# M1 设计：验收与跨 spec 契约

- 状态：草案
- 日期：2026-11-16
- 级别：T3
- 依据：[requirements.md](requirements.md) AC-30~49；[ADR-0005](../../adr/0005-enterprise-boundary.md)、[ADR-0006](../../adr/0006-customer-login.md)
- 说明：S2 首版评审不通过（B-01~B-12）后重写。`003` 只保留 M1 验收与跨 spec 契约；实现设计在 `004`/`005`/`006`。
- 前置决策：[s2-decisions.md](s2-decisions.md)（先定数据/actor/legacy/范围/保留）。

## 1. Spec 关系

| Spec | 角色 | 内容 |
|---|---|---|
| `003`（本文件） | M1 验收 / 共享契约 | AC-30~49、数据所有权、actor/trace、状态机、迁移/快照/回滚、端到端评测 |
| `004-m1-customer-chat` | 实现 spec（T3） | 客户登录/session、AI 回复、订单按账号查询、转人工创建、客户前端 |
| `005-m1-agent-workspace` | 实现 spec（T3） | 员工认证/RBAC、队列/领取/接管/回复/关闭、工作台前端 |
| `006-m1-cancellation` | 实现 spec（T3） | 客户/坐席取消 actor、确认、幂等、Workflow |

- `003` 是唯一 AC 来源；`004/005/006` 不新增 AC，只引用 003 的 AC 子集。
- 每个实现 spec 仍需 S2 设计评审、S3 任务地图、S4 执行卡；S1 只写“实现范围 + AC 引用”，不重复 AC。
- M1 出口仍由 003 的端到端验收决定。

## 2. 模块与依赖

```text
services/
  api/                 # customer_routes.py / workspace_routes.py；legacy 保留 M1-P
  conversations/       # 会话、消息、交接单、队列、领取/接管
  identity/            # 员工账号/session/RBAC；legacy 内存账号保留给 001 测试
  platform/            # settings/db/models/observability/outbox/worker/ratelimit/retention
  domain/              # orders/cancellation/errors
  agent_runtime/       # 模型调用、意图、confidence、Tool 规划
  tools/               # ToolGateway、query/cancel/policy
  workflows/           # 取消 Workflow（006 扩展 actor）
  adapters/oms/        # OmsPort + Mock/Http + factory
```

依赖规则：

- `api` → `conversations`/`identity`/`platform`/`agent_runtime`/`tools`/`workflows`/`adapters.oms.port`。
- `conversations` → `platform`/`identity`/`domain`/`agent_runtime`/`tools`/`workflows`/`adapters.oms.port`；不得 import `api`。
- `agent_runtime` → `domain`/`contracts`/`platform`/`identity`（仅类型）/`tools`；不得 import `api`/具体 Adapter。
- `tools`/`workflows` → `domain`/`identity`/`platform`/`adapters.oms.port`；不得 import `conversations`/`api`/具体 Adapter。
- `identity` → `platform`；不 import `conversations`/`tools`/`workflows`。
- `platform` → 标准库/第三方；不 import 业务模块。
- `apps/*` 只经 HTTP + `packages/contracts`；客户 app 不含员工认证。

`check-imports.py` 增加 **R7**：`services/conversations` 禁止 `services.api`、具体 OMS Adapter、`sqlalchemy` 直连（只能经 platform 仓储）；`agent_runtime` 禁止 `api`/具体 Adapter（已有 R1/R2 扩展）。

## 3. 数据所有权与迁移

**M1 使用新的 `service_*` 表**，M1-P 的 `conversations`/`messages`/`handoffs`/`cancellation_requests`/`audit_events` 原样保留，旧路由/旧测试不受影响；M1-P 数据不再写入。这样避免 M1 客户账号与旧表 `user_id` 语义/唯一约束冲突，也避免修改旧表导致 001 测试与 R0-2 快照静默漂移。

| 表 | 关键列/约束 |
|---|---|
| `service_customers` | id、tenant_id、username、password_hash、display_name、oms_user_id、active、created_at；UNIQUE(tenant_id, username)、UNIQUE(tenant_id, oms_user_id) |
| `service_customer_sessions` | id、customer_id、token_hash UNIQUE、created_at、expires_at、revoked_at、last_seen_at |
| `service_conversations` | id、tenant_id、customer_id、status、assigned_agent_id?、journey_id、created_at、updated_at、closed_at? |
| `service_messages` | id、conversation_id、author_type（customer/ai/agent/system）、author_id?、content、trace_id、created_at |
| `service_handoffs` | id、tenant_id、conversation_id、customer_id、status、reason、priority、summary、context、verified_order_ids、pending_step、claimed_by?、claimed_at?、version、journey_id、created_at、updated_at |
| `service_employees` | id、tenant_id、username、password_hash、role、display_name、active；UNIQUE(tenant_id, username) |
| `service_employee_sessions` | id、employee_id、token_hash UNIQUE、created_at、expires_at、revoked_at |
| `service_cancellation_requests` | 006 定义；actor/确认/幂等字段 |
| `service_model_events` | id、conversation_id、journey_id、event_type、name、status、confidence?、trace_id、created_at |
| `service_tool_events` | id、conversation_id、journey_id、tool_name、status、error_code、latency_ms、trace_id、created_at |
| `service_audit_events` | id、tenant_id、actor_type、actor_id、event_type、entity_type/id、result_status、journey_id、trace_id、metadata_redacted、created_at |
| `service_outbox_events` | id、event_type、aggregate_type/id、payload、status、attempts、available_at、created_at、processed_at |
| `service_rate_limit_buckets` | bucket_key、window_start、count；PK(bucket_key, window_start) |

关键约束：

- `service_handoffs` 部分唯一索引：`UNIQUE (tenant_id, conversation_id) WHERE status IN ('QUEUED','CLAIMED','ACTIVE')`，保证同一会话同一时刻一张 open 交接单；转回 AI/关闭必须先终态旧单。
- 新行默认 `status='QUEUED'`、`version=0`、`reason/priority` 非空；旧数据不迁移。
- `service_conversations` 部分唯一索引：`UNIQUE (tenant_id, customer_id) WHERE status <> 'CLOSED'`，保证一个客户同时只有一个未关闭会话；登录恢复该会话。
- 客户账号停用后保留审计；M1 不做删除/注销。

迁移全部加法；不修改旧表；Alembic 只创建新表/索引。R0-2 的 DB/OpenAPI 快照策略见第 11 节。

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
| `CLOSED` | 任意写 | 409 `CONVERSATION_CLOSED` | — |

- 一个客户同时只有一个未关闭会话（部分唯一索引兜底）；登录恢复。
- `AI_ACTIVE` 空闲 24h 自动关闭；`QUEUED/CLAIMED/HUMAN_ACTIVE` 不因 24h 自动关闭。

### 4.2 交接单

`QUEUED → CLAIMED → ACTIVE → CLOSED`，与会话状态同事务更新。`CLOSED` 后队列不再返回。

### 4.3 排队/接管中的客户消息

- `QUEUED`/`CLAIMED`/`HUMAN_ACTIVE`：客户消息持久化为 `author_type=customer`，不进入 AI，不新建交接单；坐席领取后可读。
- 重复转人工：已有 open 交接单时返回既有单，不新建（部分唯一索引兜底）。
- 转回 AI：旧交接单→`CLOSED`、`assigned_agent_id=NULL`、写系统消息/审计；下一轮低置信可新建交接单。

### 4.4 员工 session

`ACTIVE → EXPIRED/REVOKED`；8h 绝对过期；登录轮换撤销同员工旧 session；登出立即撤销。

## 5. Actor 与访问上下文

```python
@dataclass(frozen=True)
class Actor:
    tenant_id: str
    actor_type: Literal["customer", "agent"]
    actor_id: str  # customer_id 或 employee_id
    customer_id: str | None = None
    employee_id: str | None = None


@dataclass(frozen=True)
class ToolContext:
    actor: Actor
    oms_access: OmsAccess
    trace_id: str
    journey_id: str
```

- 客户 `oms_access = OmsAccess(tenant, user_id=customer.oms_user_id)`；订单按账号归属，不使用会话授权表。
- 坐席 `oms_access = OmsAccess(tenant, user_id=None, verified_order_ids=handoff.verified_order_ids)`；不把坐席当订单归属用户。
- `ToolGateway.invoke(name, payload, context)`；Tool handlers 用 `context.oms_access`；审计记录 `context.actor`。
- 旧 M1-P 路径用 `ToolContext` 适配器由 `Identity` 构造，保持 001 测试；新 M1 不依赖旧 `Identity`。
- 取消 actor 由 `006` 扩展：`service_cancellation_requests` 记 `customer_id`、`requested_by`、`confirmed_by`；坐席不能写 `confirmed_by`。

## 6. 交接单契约

- 触发由确定性 `HandoffPolicy` + 模型输出：显式转人工、`MANUAL_REVIEW`、同一取消任务连续 2 次 OMS Timeout/Connection、`SUBMIT_UNKNOWN`、模型 10s 超时、置信度 <0.6；优先级按 requirements 6.1。
- 创建与会话 `AI_ACTIVE→QUEUED` 同事务；写 customer_id、summary（≤500 字）、context（最近 20 条且≤4000 字）、verified_order_ids、pending_step、reason、priority、journey_id。
- 摘要可由模型起草，字段/裁剪/脱敏由服务端补齐；脱敏清单按 requirements 6.8。
- 队列摘要字段：handoff_id、conversation_id、等待秒数、reason、priority、订单数、脱敏末条（≤100 字）；不返回完整消息/订单。
- `QUEUED` 持久化；无坐席领取不丢失；30d 清理只对终态交接单生效（见第 8 节）。

## 7. Trace、审计、outbox 与事务归属

| 动作 | 写什么 | 谁 commit |
|---|---|---|
| 客户消息 | `service_messages`、`service_model_events`/`service_tool_events`、`service_audit_events` | Conversation service（一次事务） |
| 转人工 | `service_handoffs` + `service_conversations` 状态 + audit/outbox | Conversation service |
| 领取 | handoff/conversation 状态 + audit/outbox | Queue service |
| 接管 | conversation/handoff + 系统消息 + audit/outbox | Queue service |
| 回复 | message + audit | Conversation service |
| 请求取消/确认 | 006 表 + audit/outbox | Cancellation service |
| 关闭/转回 | conversation/handoff + audit/outbox | Conversation service |

- 审计/outbox 与业务写同事务；审计写失败 → 503，业务回滚；不得先提交消息再报审计失败。
- 每个会话稳定 `journey_id`；每个请求 `trace_id`；消息/Tool/模型事件/交接/领取/接管/取消/关闭共享 journey。
- 401/403/429、订单校验失败、越权/跨租户探测写 `service_audit_events`（安全事件）。
- AI 轨迹 = `service_model_events` + `service_tool_events`；不存请求/响应正文。
- outbox 由 `services/platform/worker` 消费；M1 至少持久化 + 幂等消费；无消费者时只写不投递（设计明确）。

## 8. 保留与清理

| 数据 | 条件 | 处理 |
|---|---|---|
| `service_customer_sessions` | `expires_at < now` | 硬删除 |
| `service_customers` | 停用后保留审计 | M1 不删除；`active=false` 拒绝登录 |
| `service_employee_sessions` | `expires_at < now` | 硬删除 |
| `service_messages` | 所属会话 `closed_at + 30d < now` | 硬删除 |
| `service_handoffs` | 终态且 `updated_at + 30d < now` | 硬删除；open 单永不静默删除 |
| `service_model_events`/`service_tool_events` | 会话终态 +30d | 硬删除 |
| `service_audit_events` | `created_at + 90d < now` | 归档到冷存储后删除；M1 归档介质在 005 S2 定 |
| `service_rate_limit_buckets` | 窗口过期 | 删除 |
| `service_outbox_events` | `processed_at + 30d` | 删除 |

- open `QUEUED/CLAIMED/HUMAN_ACTIVE` 交接单不因 30d 被删；超时告警，人工处理。
- 完整手机号从不落库/日志；订单授权只存 `order_id`。
- worker 可注入时钟、批大小、租约、幂等键；失败告警。

## 9. 认证与限速契约（005 细化）

- 客户登录：预置账号 + scrypt 密码；登录失败 5/15min/账号+IP；客户 session 256-bit token、SHA-256 存储、24h 绝对过期、Cookie `csid` `HttpOnly/SameSite=Lax/Secure(prod)/Max-Age=86400/Path=/`；登录轮换，旧 token 撤销。一个客户一个未关闭会话。
- 员工：scrypt（N=2^14,r=8,p=1）、8h、登录轮换撤销旧 session、登出立即失效；不存在账号做 dummy scrypt；username 规范化（trim/lower）+ 长度上限。
- 限速：PostgreSQL 桶；key→阈值/窗口：`msg:{customer_session}` 30/min；`customer_login:{norm_user}:{ip}` 5/15min；`employee_login:{norm_user}:{ip}` 5/15min；IP 只取直连 peer 或可信代理配置，不信任裸 `X-Forwarded-For`；限速先于业务副作用；429 `RATE_LIMITED` + `Retry-After`。

## 10. API 边界

- 客户：`POST /customer/sessions`（登录）、`GET /customer/session`、`/customer/messages`、`/customer/conversations/{id}/messages`（带 id 的读取用于隔离测试）、`/customer/orders`、`/customer/orders/{id}`、`/customer/orders/{id}/cancellations`、`/customer/handoff`、`/customer/session/close`。
- 坐席：`/workspace/sessions`、`/workspace/queue`、`/workspace/queue/{handoff}/claim`、`/workspace/conversations/{id}/takeover`、`/workspace/conversations/{id}`、`/workspace/conversations/{id}/messages`、`/workspace/conversations/{id}/cancellations`、`/workspace/conversations/{id}/close`、`/workspace/conversations/{id}/return-to-ai`。
- 旧 M1-P 路径保留在 `services/api/legacy/`，仅测试/归档使用；生产不挂载（或 `M1_ENABLED` 控制新路径，旧路径不作为生产回滚身份）。
- 客户按 `order_id` 查询：未登录 401、他人/跨租户 404；客户按 conversation id 读取：非本人 404。

## 11. 快照、兼容与 CI

- **旧表/旧路由不动**：001 测试与 R0-2 行为保持。
- R0-2 AC-27/28 测试改为**子集兼容**：旧 OpenAPI 路径/组件、旧 DB 表必须保持；新增 M1 路径/表允许。另加 `openapi-m1.json`、`db-schema-m1.json` 全量快照测试。快照重基线是显式决策，记录在 003 S2 评审。
- `verify.sh` 增加 `apps/chat`、`apps/workspace` 的 lint/typecheck/test；`evals/run.py` 增加 AC-30~49 与 M1 场景；`check-route-coverage.py` 覆盖新路由。
- `M1_ENABLED` 加入 `Settings`：development/test 默认 true，production 默认 false；关闭时不挂载 `/customer`/`/workspace` 与 worker。

## 12. 回滚

- 目标：关闭 `M1_ENABLED` → 回滚代码到 M1 前版本 → 旧版本可运行；M1 新表保留不删，重新启用可直接续用。
- 迁移全部加法；不 downgrade 旧表。若必须删新表，先备份，需人工批准。
- 旧 M1-P 路由不作为生产回滚身份（生产 test_accounts 关闭）；回滚目标是上一个 release，而不是切回 M1-P。
- 演练：临时库 upgrade→应用启动→关闭 M1_ENABLED→旧版本验证；记录 SHA/命令/退出码。

## 13. T3 威胁模型与越权矩阵

| 威胁 | 控制 | 验证 | 残余风险/接受人 |
|---|---|---|---|
| 登录爆破/撞库 | scrypt、登录限速、非枚举、账号停用 | AC-30/47 | 弱密码（安全负责人，待批准） |
| 会话伪造/固定 | 随机 token/哈希/轮换/Cookie 属性 | AC-30/49 | 设备被控（安全负责人，待批准） |
| 跨会话/跨租户 | 服务端 ownership、404 | AC-33/49 | 内部误配（待批准） |
| 队列抢占/双坐席 | 部分唯一索引、条件更新、租户条件 | AC-39/40 | DB 故障（待批准） |
| 取消代确认 | 客户 confirmed_by、坐席 403、30min worker | AC-42 | 社工（待批准） |
| 审计篡改/遗漏 | 同事务、只读、无删除、安全事件 | AC-45 | DBA（待批准） |
| PII 泄露 | 新表最小字段、脱敏、无完整手机号 | AC-36/46 | 用户输入（待批准） |
| 清理遗漏 | worker 矩阵、open 单排除、告警 | AC-44/46 | 运维（待批准） |
| 内部人员滥用 | RBAC、最小权限、审计 | AC-38/45 | 账号共享（待批准） |
| DoS/限速绕过 | PG 桶、可信 IP、限速先行 | AC-47 | 分布式 IP（待批准） |
| CSRF/Origin | 复用 verify_origin 白名单 | AC-47 | 开发跨端口（待批准） |
| 重放/重复取消 | 幂等键/唯一约束/状态机 | AC-34/42 | 客户端重试（待批准） |

越权矩阵沿用 requirements 6.3/6.4 与 003 第 10 节；每个实现 spec 的 S2 必须给出端点级矩阵与测试。

## 14. 实现 spec 与 AC 映射

| Spec | AC |
|---|---|
| 004 客户聊天 | AC-30、31、32、33、35、36、44、46、47、49；AC-48 客户路径 |
| 005 坐席工作台 | AC-37、38、39、40、41、43、45、46、47；AC-48 坐席路径 |
| 006 取消 | AC-34、42；AC-48 取消路径 |

## 15. 开放项（必须由子 spec S2 关闭）

- 队列位置/SLA 文案（004/005）。
- 模型成本/延迟（004）。
- 密码策略/种子账号（005）。
- 审计归档介质/清理频率（005）。
