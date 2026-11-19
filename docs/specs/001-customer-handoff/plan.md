# 客户转人工闭环 plan

> 结构依据：Google Design Doc（Context and Scope / Goals and Non-Goals / The Design / Alternatives Considered / Cross-cutting Concerns）。
> 页数：T3 按需扩展，只写关键签名/约束，不抄完整 API/schema。

- 状态：已批准
- 批准：2026-11-17（用户确认 Q-1~Q-3；结构重排不改变已批准范围/AC）
- 日期：2026-11-17
- 作者 / 评审者：实现者 / 独立上下文
- 依据：`brief.md`、[ADR-0006](../../adr/0006-customer-login.md)
- 规模：T3（客户/员工认证、会话归属、队列权限、审计）

## 1. 背景与范围（Context and Scope）

本切片是 M1 第一条垂直切片，证明客户登录 → AI 对话 → 消息触发转人工 → 坐席领取/接管/回复 → 关闭或转回 AI 的端到端闭环。垂直切片与 blocking edge 见 `brief.md` 附录 B；可执行 feature 见 `features.md`（本 plan 批准后生成）。

- 问题与现状：M1-P 只有原型级匿名会话与查询/取消；企业 M1 需要真实客户/员工身份、会话归属、队列与审计。当前没有可走的人工路径，坐席侧没有队列、接管动作和上下文。
- 为什么现在做：订单查询（003）、取消（004）都依赖会话/身份/队列/审计基座；先证明转人工闭环，后续切片才能复用（2026-11-18 编号顺延：UI 改版占 002）。
- 本设计覆盖：客户登录/会话、AI 对话、消息触发转人工、坐席登录/队列/领取/接管/回复/关闭/转回、客户甲/乙对等、审计/限速、T3 威胁模型与回滚。
- 本设计不覆盖：订单查询/取消、历史会话、客户注册/OTP/MFA、主管/管理员、自动分配、真实 OMS、WebSocket/SSE、保留清理、全量评测。
- 相关 ADR / 不变量：ADR-0006（预置账号 + 密码登录）；多租户隔离、服务端授权、审计不可改删；前端只展示，不承载授权。

## 2. 目标与非目标（Goals and Non-Goals）

> 产品目标与非目标见 `brief.md`；这里只写本设计的目标。

### Goals

- 一条会话可在 AI/队列/人工之间可逆转换：`AI_ACTIVE → QUEUED → CLAIMED → HUMAN_ACTIVE → CLOSED/AI_ACTIVE`，每次转换有审计。
- 客户与坐席各自认证；客户只能访问自己的会话，坐席只能访问领取/接管后的会话；跨租户/越权 404。
- 交接单带足够上下文（摘要、最近 20 条消息、AI 轨迹、原因、待办），领取前不泄露完整消息。
- 并发领取只有一个成功；同一会话不出现两张 open 交接单；一个客户只有一个未关闭会话。
- 模型失败不阻断客户：单次超时/异常先返回可重试提示；同一会话连续两次失败或客户要求时自动转人工；审计失败则业务回滚（503）。

### Non-Goals

- 不做订单 Tool/真实 OMS；本切片 `order_count=0`。
- 不做自动分配、主管/管理员视图、历史会话、客户注册/OTP/MFA。
- 不做 WebSocket/SSE；3s 轮询先证明闭环。
- 不做服务端阻塞式重试或多模型自动切换；重试由客户触发，连续失败才转人工。
- 不做保留清理、全量评测、outbox；后续切片再引入。

## 3. 方案（The Design）

### 3.1 总体方案与模块边界

```text
apps/chat/                 # 客户 Web Chat（Next app）
apps/workspace/            # 坐席工作台（Next app）
apps/web/                  # M1-P 归档，不再作为 M1 入口

backend/api/               # 应用装配、中间件、共享错误与审计编排
  main.py
  admin_routes.py          # 仅开发/测试的 Mock OMS 故障注入
backend/conversations/     # 会话、消息、交接单、队列、转人工策略
  customer_http.py         # /customer/* 入口
  workspace_http.py        # /workspace/* 业务入口
  schemas.py               # 客户与工作台 DTO
backend/identity/          # 客户/员工账号、session、RBAC
  http.py                  # /workspace/* 认证入口
  customer_auth.py         # 客户认证依赖
  employee_auth.py         # 员工认证依赖
  schemas.py               # 员工登录与会话 DTO
backend/audit/             # 审计写入
backend/platform/          # db/models/settings/http/observability/ratelimit
backend/agent_runtime/     # 模型契约与类型（旧 Web 接口与对话编排已退役，保留 model/types 供现役链路）
backend/tools/             # 查询/取消 Tool（保留供 003/004 接入）
backend/workflows/         # 取消工作流（保留供 004 接入）
```

- 依赖：`api → conversations/identity/platform`（仅装配）；`conversations → identity/platform/agent_runtime`；`identity → platform`；`platform` 不依赖业务模块。
- `conversations` 不 import `api` 之外的具体业务模块、具体 OMS Adapter。
- 前端只展示，不承载授权/状态转换；两个 app 不共用页面/路由，客户 app 不含员工认证，工作台不依赖客户 cookie。
- `apps/chat`：`/login`、`/chat`；消息流、输入、排队/人工状态、关闭、登出；**无转人工按钮**；3s 轮询。
- `apps/workspace`：`/login`、`/queue`、`/conversations/[id]`；队列、领取、接管、消息、AI 轨迹、交接单摘要、回复、关闭、转回；3s 轮询。

### 3.2 数据模型与迁移

M1 使用新的 `service_*` 表；M1-P 的旧表与取消工作流保留，旧 Web 接口与对应测试已于 2026-11-19 退役。迁移只做加法。

| 表 | 关键列/约束 |
|---|---|
| `service_customers` | id、tenant_id、username、password_hash、display_name、active、created_at；UNIQUE(tenant_id, username) |
| `service_customer_sessions` | id、customer_id、token_hash UNIQUE、created_at、expires_at、revoked_at、last_seen_at |
| `service_employees` | id、tenant_id、username、password_hash、role（M1 仅 `agent`）、display_name、active；UNIQUE(tenant_id, username) |
| `service_employee_sessions` | id、employee_id、token_hash UNIQUE、created_at、expires_at、revoked_at |
| `service_conversations` | id、tenant_id、customer_id、status、assigned_employee_id?、journey_id、created_at、updated_at、closed_at?、last_activity_at |
| `service_messages` | id bigserial、conversation_id、author_type（customer/ai/agent/system）、author_id?、content、trace_id、created_at |
| `service_handoffs` | id、tenant_id、conversation_id、customer_id、status、reason、priority、summary、context、pending_step、claimed_by?、claimed_at?、version、journey_id、created_at、updated_at |
| `service_ai_events` | id、conversation_id、journey_id、event_type、name、status、confidence?、trace_id、created_at |
| `service_audit_events` | id、tenant_id、actor_type、actor_id、event_type、entity_type、entity_id、result_status、journey_id、trace_id、metadata_redacted、created_at |
| `service_rate_limit_buckets` | bucket_key、window_start、count；PK(bucket_key, window_start) |

关键约束：

- `service_conversations`：`UNIQUE (tenant_id, customer_id) WHERE status <> 'CLOSED'`，保证一个客户一个未关闭会话。
- `service_handoffs`：`UNIQUE (tenant_id, conversation_id) WHERE status IN ('QUEUED','CLAIMED','ACTIVE')`，同一会话一张 open 交接单。
- `service_messages(conversation_id, id)`、`service_handoffs(status, created_at)`、`service_audit_events(journey_id, created_at)` 索引。
- 不做 `order_access_grants`；本切片无订单。
- 种子账号：`customer_a`/`customer_b`、`agent_1`/`agent_2`；登录页不列账号。

### 3.3 API / 状态机 / 并发

#### 3.3.1 状态机与并发

| From | 动作 | To | 执行者 |
|---|---|---|---|
| `AI_ACTIVE` | 转人工 | `QUEUED` | 客户/策略 |
| `AI_ACTIVE` | 客户结束 | `CLOSED` | 客户 |
| `QUEUED` | 领取 | `CLAIMED` | 坐席 |
| `QUEUED` | 客户结束 | `CLOSED` | 客户 |
| `CLAIMED` | 接管 | `HUMAN_ACTIVE` | 领取坐席 |
| `CLAIMED` | 关闭 | `CLOSED` | 领取坐席 |
| `CLAIMED` | 客户结束 | `CLOSED` | 客户 |
| `HUMAN_ACTIVE` | 回复 | `HUMAN_ACTIVE` | 接管坐席 |
| `HUMAN_ACTIVE` | 关闭 | `CLOSED` | 客户/接管坐席 |
| `HUMAN_ACTIVE` | 转回 AI | `AI_ACTIVE` | 接管坐席 |
| `CLOSED` | 任意写 | 409 `CONVERSATION_CLOSED` | — |

- 交接单状态：`QUEUED → CLAIMED → ACTIVE → CLOSED`，与会话同事务更新；关闭/转回必须终态旧交接单。
- 一个客户同时只有一个未关闭会话；登录恢复；不做历史列表。
- `AI_ACTIVE` 空闲 24h 自动关闭：在登录、`GET /customer/session`、发消息时惰性检查 `last_activity_at + 24h < now`，同事务关闭；本切片不引入后台 worker。`QUEUED/CLAIMED/HUMAN_ACTIVE` 不因 24h 自动关闭。
- 客户可在任意未关闭状态关闭；交接单/队列同事务关闭。
- 转回 AI 后同一会话恢复历史；再次转人工新建交接单，旧单必须已终态。
- 同一会话同一时刻只有一个 `CLAIMED/HUMAN_ACTIVE` 坐席；部分唯一索引兜底。

#### 3.3.2 认证与 session

- 客户：`POST /customer/sessions` 用户名/密码；scrypt（N=2^14,r=8,p=1，16-byte salt）；24h 绝对过期；登录轮换 token；登出撤销。
- 员工：`POST /workspace/sessions`；8h 绝对过期；登录轮换撤销同员工旧 session；登出撤销；M1 仅 `agent`。
- Cookie：客户 `csid`、员工 `esid`；`HttpOnly`、`SameSite=Lax`、生产 `Secure`、`Max-Age`、`Path=/`。
- token：256-bit 随机，存 SHA-256；不存明文。
- 不存在账号做 dummy scrypt；登录失败统一 401，超限 429；不泄露账号存在性。
- 一个客户一个未关闭会话；登录时查找 `status <> 'CLOSED'` 的会话，有则恢复，无则新建。

#### 3.3.3 API

**客户**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/customer/sessions` | 登录；返回客户/会话/状态；Set-Cookie |
| DELETE | `/customer/sessions` | 登出，撤销 session |
| GET | `/customer/session` | 当前客户、会话、状态、`after_id` |
| GET | `/customer/conversations/{conversation_id}` | 按所有权读取指定会话；他人/不存在 404（AC-30、AC-33） |
| POST | `/customer/messages` | 发消息；返回新消息 + AI 回复/排队状态 |
| GET | `/customer/messages?after_id=` | 轮询消息 |
| POST | `/customer/session/close` | 客户关闭任意未关闭会话 |

**坐席**

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/workspace/sessions` | 登录 |
| DELETE | `/workspace/sessions` | 登出 |
| GET | `/workspace/queue` | 队列摘要 |
| POST | `/workspace/queue/{handoff_id}/claim` | 条件领取 |
| POST | `/workspace/conversations/{id}/takeover` | 接管 |
| GET | `/workspace/conversations/{id}` | 客户/交接单/AI 轨迹/待办 |
| GET | `/workspace/conversations/{id}/messages?after_id=` | 轮询消息 |
| POST | `/workspace/conversations/{id}/messages` | 回复 |
| POST | `/workspace/conversations/{id}/close` | 关闭 |
| POST | `/workspace/conversations/{id}/return-to-ai` | 转回 AI |

- 错误封套 `{code, retryable, visible, message}`；错误码：401 `SESSION_INVALID`/`SESSION_EXPIRED`/`AUTH_FAILED`、403 `FORBIDDEN`、404 `NOT_FOUND`、409 `CLAIM_CONFLICT`/`CONVERSATION_CLOSED`、422 `VALIDATION_ERROR`、429 `RATE_LIMITED`、503 `AUDIT_UNAVAILABLE`。
- 轮询每 3s，`after_id` 为消息 ID；无 WebSocket/SSE。
- 客户消息限制长度；坐席回复限制长度；422 不产生副作用。

#### 3.3.4 AI 与转人工

- 关键词（normalize 后）：`转人工`、`人工客服`、`真人`、`找人工`；命中直接创建 `CUSTOMER_REQUEST` 交接单，不调用模型。
- 未命中：`agent_runtime` 调用模型，返回 `{intent, confidence, reply}`；失败按类型分流：

| 类型 | 触发 | 处理 |
|---|---|---|
| `CUSTOMER_REQUEST` | 关键词或 `intent=transfer` | 建交接单 |
| `LOW_CONFIDENCE` | `confidence < 0.6` | 建交接单 |
| `OUT_OF_SCOPE` | 订单/超范围 | 建交接单 |
| `MODEL_TIMEOUT` | 模型 10s 超时 | 单次：提示重试，不建单；同一会话连续 2 次：建单，reason=`MODEL_UNAVAILABLE` |
| `MODEL_ERROR` | 模型异常/5xx | 同 `MODEL_TIMEOUT` |
| `TOOL_FAILED` | 工具报错/超时（003/004 接入后） | 只读查询：提示重试；有副作用的动作：建单并带动作/错误 |

- 单次模型失败不建单：写系统消息「AI 暂时不可用，你可以重试，或说“转人工”。」；客户重发或明确说“转人工”后按对应路径处理。
- 同一会话连续 2 次 `MODEL_TIMEOUT`/`MODEL_ERROR`：自动建单，系统消息改为「AI 暂时不可用，已为你转接人工（排队中）。」，避免客户反复失败无出口。
- 「连续」指同一会话相邻两条客户消息均失败，中间没有成功的 AI 回复；成功回复后失败计数清零。
- 本切片没有订单 Tool；AI 不得编造订单信息；超范围直接转人工。
- 交接单：customer_id、summary≤500、context（最近 20 条且≤4000 字）、AI 轨迹、reason、priority、pending_step；`order_count=0`；脱敏；连续失败时记录失败次数与最后一次错误码。
- AI 轨迹写 `service_ai_events`：`event_type`（model/intent）、name、status、confidence、trace_id；不存 prompt/response 正文。

#### 3.3.5 队列与接管

- 队列：`status='QUEUED'`，`ORDER BY created_at, id`；摘要：handoff_id、conversation_id、客户账号/显示名、等待秒数、reason、order_count=0、脱敏末条≤100 字。
- 领取：`UPDATE service_handoffs SET status='CLAIMED', claimed_by=:me, claimed_at=now(), version=version+1 WHERE id=:id AND tenant_id=:tenant AND status='QUEUED' RETURNING ...`；无行 → 404/409。
- 领取同事务：`service_conversations.status='CLAIMED'`、`assigned_employee_id=:me`、审计。
- 接管：`WHERE id=:id AND claimed_by=:me AND status='CLAIMED'`；设 `HUMAN_ACTIVE`/`ACTIVE`，写系统消息“人工已接入”，审计；无行 404。
- 同一会话同一时刻只有一个 `CLAIMED/HUMAN_ACTIVE` 坐席；部分唯一索引兜底。

### 3.4 失败路径与用户可见文案

| 场景 | 客户看到 | 坐席看到 |
|---|---|---|
| 登录失败 | 账号或密码不正确 | — |
| 客户转人工 | 排队中，请稍候 | 队列出现该客户 |
| 模型连续失败自动转人工 | AI 暂时不可用，已为你转接人工（排队中） | 队列出现该客户，交接单带失败次数/错误码 |
| 坐席领取后 | 正在接入人工 | 会话归我 |
| 坐席接管后 | 人工已接入 | 会话归我 |
| 会话关闭后再发 | 会话已结束 | 只读 |
| 队列为空 | — | 暂无待接入会话 |
| 请求过频 | 请求过于频繁，请稍后再试 | — |

事务与失败：

| 动作 | 写什么 | 失败 |
|---|---|---|
| 客户发消息 | message + audit | 422/503，不产生半条 |
| AI 回复 | AI message + ai_event + audit | 单次失败 → 可重试提示；连续 2 次失败 → 交接单 |
| 创建交接单 | handoff + conversation 状态 + audit | 同事务回滚 |
| 领取/接管 | handoff + conversation + 系统消息 + audit | 409/404 |
| 回复 | message + audit | 503 回滚 |
| 关闭/转回 | conversation + handoff + 系统消息 + audit | 409/503 |

## 4. 备选方案（Alternatives Considered）

| 决策 | 选择 | 备选 | 备选优点 | 备选缺点 | 不选备选的原因 |
|---|---|---|---|---|---|
| 转人工触发 | 消息 + 关键词/模型 intent | 按钮 | 明确、可控 | 多一个 UI 控件，客户要先找到按钮 | 客户用自然语言就能切换；少一个控件 |
| 模型失败处理 | 单次提示重试、连续 2 次失败转人工 | 模型失败一律自动转人工（原方案） | 简单、永不卡住 | 瞬时故障也占队列，客户不知情 | 超时属基础设施故障，先重试/降级；人工是最后兜底（ADR-0011） |
| 前端 | 两个 Next app | 一个 app 两个路由 | 复用脚手架 | 客户/员工认证与部署边界混在一起 | 两个 app 的认证与部署边界更清楚 |
| 数据 | 新 `service_*` 表 | 复用 M1-P 旧表 | 少建表 | 旧 `user_id`/唯一约束会把本切片拖回兼容债 | 新表避免兼容债；旧表保留，旧 Web 路由已退役 |
| 队列 | 领取优先 | 自动分配 | 坐席不用抢 | M1 没有 presence/分配规则 | 先证明领取/接管闭环，分配规则后续再加 |
| 客户关闭 | 任意未关闭状态可关 | 仅坐席可关 | 坐席可控 | 客户被卡在队列里 | 客户不能被卡住；关闭同事务收口交接单 |
| 空闲关闭 | 登录/读状态时惰性检查 | 后台 worker | 关闭更准时 | 引入 worker/调度 | 本切片不引入 worker；惰性检查足够 |
| 消息更新 | 3s 轮询 + `after_id` | WebSocket | 实时性更好 | 连接/重连/部署复杂 | 先证明闭环，不做实时推送 |

## 5. 跨切面关注点（Cross-cutting Concerns）

### 5.1 安全、权限与审计

- 认证/授权/租户隔离：见 3.3.2；所有资源查询带 `tenant_id` + ownership，越权统一 404。
- 审计事件：`customer.login/logout`、`employee.login/logout`、`handoff.created/claimed`、`conversation.taken_over`、`message.sent`、`message.replied`、`ai.replied`、`conversation.closed/returned_to_ai`、`conversation.viewed`、`auth.failed`、`rate_limited`、`forbidden`。F-01 只做认证/session；审计统一由 F-13/AC-39 落地。
- 审计与业务写同事务；审计失败 → 503，业务回滚；审计只读，无删除接口。
- 限速：PostgreSQL 桶；`customer_login:{username}:{ip}` 5/15min、`employee_login:{username}:{ip}` 5/15min、`msg:{customer_session}` 30/min；429 `RATE_LIMITED` + `Retry-After`；限速先于业务副作用。
- IP 只取直连 peer 或可信代理配置；不信任裸 `X-Forwarded-For`。
- CSRF/Origin：复用 `verify_origin` 白名单。

**T3 威胁模型**

| 威胁 | 控制 | 验证 |
|---|---|---|
| 登录爆破/撞库 | scrypt、dummy hash、5/15min、非枚举 401/429 | AC-30/34/39 |
| 会话伪造/固定 | 256-bit token、哈希、轮换、Cookie 属性、24h/8h | AC-30/34/39 |
| 跨客户/跨租户 | 服务端 ownership、404 | AC-33/39 |
| 队列抢占/双坐席 | 条件更新、部分唯一索引、409/404 | AC-35/36 |
| 接管越权 | `claimed_by=me` + 状态 | AC-36 |
| 审计篡改/遗漏 | 同事务、只读、无删除、401/403/429 事件 | AC-39 |
| 限速绕过 | PG 桶、可信 IP、限速先行 | AC-39 |
| CSRF/Origin | 复用 verify_origin 白名单 | AC-39 |
| 重放 | 状态机 + 409 + 幂等读 | AC-38/39 |

**越权矩阵**

| 资源/动作 | 客户 | 未登录 | agent（同租户） | agent（他租户） |
|---|---|---|---|---|
| 自己的会话/消息 | 允许 | 401 | 仅领取/接管后 | 404 |
| 他人会话/消息 | 404 | 401 | 404 | 404 |
| 队列摘要 | 403 | 401 | 允许 | 空/404 |
| 领取/接管 | 403 | 401 | 条件允许 | 404 |
| 审计 | 禁止 | 401 | 只读本人会话 | 404 |

### 5.2 可观测性与测试 seam

| AC | 事实/契约 | 测试 seam（方式；具体命令在 features 的 Steps） |
|---|---|---|
| AC-30 | 客户登录/session/恢复 | API + Cookie + fake clock + `X-Request-ID` |
| AC-31 | AI 回复/模型失败 | `FakeModelClient` 正常/失败/低置信 |
| AC-32 | 转人工意图 | 关键词/模型/低置信/超范围 |
| AC-33 | 客户甲/乙对等 | 2 客户/2 坐席 |
| AC-34 | 员工登录/RBAC | API + 越权 |
| AC-35 | 队列/领取 | 并发 claim、FIFO、跨租户 |
| AC-36 | 接管/上下文 | 状态机 + 系统消息 + 404/409 |
| AC-37 | 回复/轮询 | message + after_id |
| AC-38 | 关闭/转回 | 客户任意状态 + 再次转人工 |
| AC-39 | 审计/限速 | 审计失败注入 + 429 + 401/403 |
| 前端 | 两个 app 的登录/聊天/队列/会话 | 人工走查 |

- `trace_id`/`journey_id` 贯穿消息、AI 事件、审计；AI 轨迹不存 prompt/response 正文与 PII。
- 测试按 AC 命名，`trace.py` 据此生成追溯矩阵；未覆盖的 AC 在 `scripts/trace-baseline.txt` 登记，测试落地后删除。

### 5.3 风险、回滚与发布

- 主要风险：并发领取/接管竞态、模型超时/不可用、审计写失败、迁移回滚。对应控制：条件更新 + 部分唯一索引；10s 超时 + 有界重试/提示，同一会话连续 2 次失败才自动转人工；同事务 503 回滚；只加法迁移。
- 回滚：`M1_ENABLED` 控制新路由与两个 app；关闭时不挂载。M1-P 旧 Web 接口已于 2026-11-19 退役，代码回退依赖 git 历史；取消工作流与旧表保留。
- 迁移只加法；回滚代码不删表；回滚目标是上一个 release。
- 不做保留清理/outbox；B/C/D 再引入。

### 5.4 其他跨切面

- 性能/容量：本切片 2 客户/2 坐席；3s 轮询；无 WebSocket/SSE。
- 成本：M1 不设成本目标；模型调用以 10s 超时封顶；成本/延迟目标在后续切片再定。
- 兼容性：M1-P 旧表与取消工作流保留，旧 Web 接口/测试已退役；新 `service_*` 表；不接真实 OMS。

## 6. 未决问题（Open Questions）

无。Q-1~Q-3 已于 2026-11-17 确认：

- Q-1 演示账号：`customer_a`/`customer_b` + `agent_1`/`agent_2`；登录页不列账号。
- Q-2 模型成本/延迟：M1 不设成本目标，只保留 10s 超时。
- Q-3 队列等待/SLA：客户只看到“排队中”，不显示位置/SLA；坐席队列仍显示等待秒数。

Q-4 UI 样式由实现者决定，不阻塞 plan。
