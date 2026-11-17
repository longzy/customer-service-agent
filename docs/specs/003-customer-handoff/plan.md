# 客户转人工闭环设计：客户 ↔ AI ↔ 人工转接闭环

- 状态：等待评审
- 日期：2026-11-17
- 依据：[brief](brief.md)、[ADR-0006](../../adr/0006-customer-login.md)
- 范围：只设计本切片；订单（004）、取消（005）、保留/全量评测（006）不做。

## 0. 人读摘要

### 0.1 目标与非目标

本切片只证明：客户登录 -> AI 对话 -> 消息触发转人工 -> 坐席领取/接管/回复 -> 关闭或转回 AI。
不做订单、取消、保留清理、全量评测。

### 0.2 两分钟故事

客户甲登录，发“我的订单到哪了”。
本切片还不支持查单，AI 回：“当前还不支持查单，我帮你转人工。”
客户甲看到“已进入队列”。
坐席 1 登录，队列看到客户甲、等待 12 秒、原因“超出当前能力”。
领取后客户甲看到“人工已接入”；坐席回复“您好，我是坐席 1”。
坐席关闭后，客户甲再发消息，看到“会话已结束”。

客户乙登录，也能完整走登录、聊天、转人工、被接管、回复、关闭、转回。

### 0.3 关键取舍

| 决策 | 选择 | 放弃 | 原因 |
|---|---|---|---|
| 转人工触发 | 消息 + 关键词/模型 intent | 按钮 | 客户用自然语言就能切换；少一个 UI 控件 |
| 前端 | 两个 Next app | 一个 app 两个路由 | 客户/员工认证与部署边界不同 |
| 数据 | 新 `service_*` 表 | 复用 M1-P 旧表 | 旧 `user_id`/唯一约束会把本切片拖回兼容债 |
| 队列 | 领取优先 | 自动分配 | M1 没有 presence/分配规则 |
| 客户关闭 | 任意未关闭状态可关 | 仅坐席可关 | 客户不能被卡在队列里 |
| 空闲关闭 | 登录/读状态时惰性检查 | 后台 worker | 本切片不引入 worker |
| 消息更新 | 3s 轮询 + `after_id` | WebSocket | 先证明闭环，不做实时推送 |

### 0.4 用户看到什么

| 场景 | 客户看到 | 坐席看到 |
|---|---|---|
| 登录失败 | 账号或密码不正确 | — |
| 客户转人工 | 已进入队列，请稍候 | 队列出现该客户 |
| 坐席领取后 | 正在接入人工 | 会话归我 |
| 坐席接管后 | 人工已接入 | 会话归我 |
| 会话关闭后再发 | 会话已结束 | 只读 |
| 队列为空 | — | 暂无待接入会话 |
| 请求过频 | 请求过于频繁，请稍后再试 | — |

### 0.5 演示脚本

1. 客户甲登录，发消息，AI 回复；发“转人工”，看到“已进入队列”。
2. 坐席 1 登录，队列看到客户甲，领取，接管；客户甲看到“人工已接入”。
3. 坐席 1 回复，客户甲 3 秒内看到；坐席关闭；客户甲再发，看到“会话已结束”。
4. 客户乙登录，重复 1–3；坐席 2 接管，证明甲乙隔离、两个坐席不抢同一会话。

## 1. 模块与依赖

```text
apps/chat/                 # 客户 Web Chat（Next app）
apps/workspace/            # 坐席工作台（Next app）
apps/web/                  # M1-P 归档，不再作为 M1 入口

services/api/
  customer_routes.py       # /customer/*
  workspace_routes.py      # /workspace/*
  legacy/                  # M1-P 路由，测试保留
services/conversations/    # 会话、消息、交接单、队列、转人工策略
services/identity/         # 客户/员工账号、session、RBAC
services/agent_runtime/    # 模型调用、intent/confidence
services/platform/         # db/models/settings/observability/ratelimit
```

依赖：`api → conversations/identity/agent_runtime/platform`；`conversations → identity/platform/agent_runtime`；`identity → platform`；`platform` 不依赖业务模块。`conversations` 不 import `api`、具体 OMS Adapter。

## 2. 数据模型

M1 使用新的 `service_*` 表；M1-P 的旧表/旧路由/旧测试原样保留。迁移只做加法。

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

## 3. 状态机

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

## 4. 认证与 session

- 客户：`POST /customer/sessions` 用户名/密码；scrypt（N=2^14,r=8,p=1，16-byte salt）；24h 绝对过期；登录轮换 token；登出撤销。
- 员工：`POST /workspace/sessions`；8h 绝对过期；登录轮换撤销同员工旧 session；登出撤销；M1 仅 `agent`。
- Cookie：客户 `csid`、员工 `esid`；`HttpOnly`、`SameSite=Lax`、生产 `Secure`、`Max-Age`、`Path=/`。
- token：256-bit 随机，存 SHA-256；不存明文。
- 不存在账号做 dummy scrypt；登录失败统一 401，超限 429；不泄露账号存在性。
- 一个客户一个未关闭会话；登录时查找 `status <> 'CLOSED'` 的会话，有则恢复，无则新建。

## 5. API

### 客户

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/customer/sessions` | 登录；返回客户/会话/状态；Set-Cookie |
| DELETE | `/customer/sessions` | 登出，撤销 session |
| GET | `/customer/session` | 当前客户、会话、状态、`after_id` |
| POST | `/customer/messages` | 发消息；返回新消息 + AI 回复/排队状态 |
| GET | `/customer/messages?after_id=` | 轮询消息 |
| POST | `/customer/session/close` | 客户关闭任意未关闭会话 |

### 坐席

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

## 6. AI 与转人工

- 关键词（normalize 后）：`转人工`、`人工客服`、`真人`、`找人工`；命中直接创建 `CUSTOMER_REQUEST` 交接单，不调用模型。
- 未命中：`agent_runtime` 调用模型，返回 `{intent, confidence, reply}`；`intent=transfer` 或 `confidence < 0.6` → `LOW_CONFIDENCE`；模型 10s 超时/异常 → `MODEL_UNAVAILABLE`；检测到订单/超范围 → `OUT_OF_SCOPE`。
- 本切片没有订单 Tool；AI 不得编造订单信息；超范围直接转人工。
- 交接单：customer_id、summary≤500、context（最近 20 条且≤4000 字）、AI 轨迹、reason、priority、pending_step；`order_count=0`；脱敏。
- AI 轨迹写 `service_ai_events`：`event_type`（model/intent）、name、status、confidence、trace_id；不存 prompt/response 正文。

## 7. 队列与接管

- 队列：`status='QUEUED'`，`ORDER BY created_at, id`；摘要：handoff_id、conversation_id、客户账号/显示名、等待秒数、reason、order_count=0、脱敏末条≤100 字。
- 领取：`UPDATE service_handoffs SET status='CLAIMED', claimed_by=:me, claimed_at=now(), version=version+1 WHERE id=:id AND tenant_id=:tenant AND status='QUEUED' RETURNING ...`；无行 → 404/409。
- 领取同事务：`service_conversations.status='CLAIMED'`、`assigned_employee_id=:me`、审计。
- 接管：`WHERE id=:id AND claimed_by=:me AND status='CLAIMED'`；设 `HUMAN_ACTIVE`/`ACTIVE`，写系统消息“人工已接入”，审计；无行 404。
- 同一会话同一时刻只有一个 `CLAIMED/HUMAN_ACTIVE` 坐席；部分唯一索引兜底。

## 8. 前端

- `apps/chat`：`/login`、`/chat`；消息流、输入、排队/人工状态、关闭、登出；**无转人工按钮**；3s 轮询。
- `apps/workspace`：`/login`、`/queue`、`/conversations/[id]`；队列、领取、接管、消息、AI 轨迹、交接单摘要、回复、关闭、转回；3s 轮询。
- 两 app 不共用页面/路由；客户 app 不含员工认证；工作台不依赖客户 cookie。
- 前端只展示，不承载授权/状态转换。

## 9. 审计与限速

- 审计事件：`customer.login/logout`、`employee.login/logout`、`handoff.created/claimed`、`conversation.taken_over`、`message.replied`、`conversation.closed/returned_to_ai`、`auth.failed`、`rate_limited`、`forbidden`。
- 审计与业务写同事务；审计失败 → 503，业务回滚；审计只读，无删除接口。
- 限速：PostgreSQL 桶；`customer_login:{username}:{ip}` 5/15min、`employee_login:{username}:{ip}` 5/15min、`msg:{customer_session}` 30/min；429 `RATE_LIMITED` + `Retry-After`；限速先于业务副作用。
- IP 只取直连 peer 或可信代理配置；不信任裸 `X-Forwarded-For`。

## 10. T3 威胁模型与越权矩阵

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

越权矩阵：

| 资源/动作 | 客户 | 未登录 | agent（同租户） | agent（他租户） |
|---|---|---|---|---|
| 自己的会话/消息 | 允许 | 401 | 仅领取/接管后 | 404 |
| 他人会话/消息 | 404 | 401 | 404 | 404 |
| 队列摘要 | 403 | 401 | 允许 | 空/404 |
| 领取/接管 | 403 | 401 | 条件允许 | 404 |
| 审计 | 禁止 | 401 | 只读本人会话 | 404 |

## 11. 事务与失败

| 动作 | 写什么 | 失败 |
|---|---|---|
| 客户发消息 | message + audit | 422/503，不产生半条 |
| AI 回复 | AI message + ai_event + audit | 模型失败 → 交接单 |
| 创建交接单 | handoff + conversation 状态 + audit | 同事务回滚 |
| 领取/接管 | handoff + conversation + 系统消息 + audit | 409/404 |
| 回复 | message + audit | 503 回滚 |
| 关闭/转回 | conversation + handoff + 系统消息 + audit | 409/503 |

## 12. 测试 seam

| 事实 | 测试 |
|---|---|
| 客户登录/session/恢复 | API + Cookie + fake clock；AC-30 |
| AI 回复/模型失败 | `FakeModelClient` 正常/失败/低置信；AC-31/32 |
| 转人工意图 | 关键词/模型/低置信/超范围；AC-32 |
| 客户甲/乙对等 | 2 客户/2 坐席；AC-33 |
| 员工登录/RBAC | API + 越权；AC-34 |
| 队列/领取 | 并发 claim、FIFO、跨租户；AC-35 |
| 接管/上下文 | 状态机 + 系统消息 + 404/409；AC-36 |
| 回复/轮询 | message + after_id；AC-37 |
| 关闭/转回 | 客户任意状态 + 再次转人工；AC-38 |
| 审计/限速 | 审计失败注入 + 429 + 401/403；AC-39 |
| 前端 | 两个 app 的登录/聊天/队列/会话；人工走查 |

## 13. S3 票映射

| 票 | AC | 主要文件 |
|---|---|---|
| T-29 | AC-30、31、32 | identity 客户/员工账号+session；conversations 会话/消息/转人工；apps/chat |
| T-30 | AC-34、35、36 | workspace 登录/队列/领取/接管；apps/workspace |
| T-31 | AC-33、37、38、39 | 回复/轮询/关闭/转回、客户甲/乙端到端、审计/限速 |

## 14. 回滚

- `M1_ENABLED` 控制新路由与两个 app；关闭时不挂载，旧 M1-P 仍保留。
- 迁移只加法；回滚代码不删表；回滚目标是上一个 release。
- 不做保留清理/outbox；B/C/D 再引入。

## 15. 开放项

- 演示账号命名、登录页文案。
- 模型配置/成本；UI 样式。
- 队列等待/SLA 展示（本切片只显示“排队中”，不做位置）。
