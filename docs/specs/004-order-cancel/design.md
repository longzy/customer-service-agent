# 订单取消 design

> 结构依据：Google Design Doc（Context/Goals/Design/Alternatives/Cross-cutting）；取舍与未决参考 Rust RFC；决策后果参考 MADR。
> 状态：已批准（2026-11-21，与 requirements 同时批准）。

- 状态：已批准
- 批准：2026-11-21（与 requirements 同时批准；F-30 起进入 Build）
- 日期：2026-11-21
- 风险级别：T3
- 依据：`requirements.md`、[总体架构](../../architecture/overview.md)、[ADR-0002](../../adr/0002-m1-order-cancel.md)、[ADR-0006](../../adr/0006-customer-login.md)、[ADR-0009](../../adr/0009-request-unit-of-work.md)、[ADR-0012](../../adr/0012-observability-grading.md)
- 模板：`docs/templates/design.md`（2026-11-21）
- 相关 ADR：ADR-0002（M1 只做未发货取消）、ADR-0009（请求级 UoW）
- 关联 features：`tasks.md`

## 1. 背景与范围（Context and Scope）

001 已交付客户登录、会话、AI 回复、转人工、队列、接管、回复、关闭/转回、审计与限速；003 已交付订单查询、订单快照、交接单订单上下文与工作台订单区。取消能力停留在 M1-P 原型：`backend/domain/cancellation.py`、`backend/tools/cancel.py`、`backend/workflows/cancel.py` 与 `cancellation_requests` 表仍在，但没有客户列表入口、客户确认入口、企业化越权与工作台衔接。

本设计覆盖：

- 客户“我的订单”独立页面与订单列表读取；
- 列表/聊天/订单号三种取消发起方式；
- 客户确认（按钮/固定短语）与 Workflow 自动提交；
- 坐席在已接管会话发起取消、客户确认后自动提交；
- 资格、越权、幂等、超时恢复、结果文案、交接单与工作台取消区、审计与 Trace。

本设计不覆盖：退款/到账（M2）、已发货拦截/拒收、改地址/换货/补发、部分取消、历史订单搜索/分页、真实 OMS、金额阈值与主管审批。M1 不区分支付方式，统一淘宝式；生产接入时按 OMS/平台规则限制（京东在线支付订单不允许商家代取消）。

相关不变量：INV-03（订单归属与 404）、INV-05（写操作由 Workflow 驱动）、INV-07（幂等键）、INV-08（超时先查）、INV-09（已提交/已受理/已取消区分）、INV-10（客户未确认不得提交）、INV-17（工作台服务端授权）。

## 2. 目标与非目标（Goals and Non-Goals）

### Goals

- 客户列表只返回本人同租户、白名单字段；越权统一“查无”。
- 取消意图确定性分流，模型不直接决定资格或提交。
- 客户确认后只提交一次；坐席发起同样由客户确认、Workflow 自动提交。
- 结果可区分“已受理/已取消/被拒绝/结果未知”，不误报退款。
- 并发、重试、超时、关闭聊天都有确定行为与可追溯记录。

### Non-Goals

- 不做退款、金额阈值审批、已发货拦截。
- 不做订单列表分页、搜索、详情页。
- 不做坐席二次提交或代确认。
- 不引入真实 OMS/支付；生产接入时按 OMS 规则限制。

## 3. 方案（The Design）

### 3.1 总体方案与模块边界

```text
客户 Web Chat（apps/chat）
  -> /orders 页面（新增）: 列表 + 每单取消按钮
  -> 确认弹层（新增）: 订单摘要 + 影响 + 有效期
  -> POST /customer/orders, /customer/cancellations...

后端 conversations 域
  -> customer_orders: 列表读取（OMS 摘要 + cancelable）
  -> customer_chat: 取消意图分流 / 固定短语确认
  -> customer_cancellations: 发起、确认、拒绝
       -> CancellationWorkflow（复用 backend/workflows/cancel.py）
            -> ToolGateway -> OmsPort（资格/提交/结果）

坐席工作台（apps/workspace）
  -> 会话详情取消区（新增）
  -> POST /workspace/conversations/{id}/cancellations（坐席发起）
```

- 客户确认后，`CancellationWorkflow` 调 `submit_cancel`；坐席没有提交/确认接口。
- 人工接管期间客户仍可在订单页自助取消；工作台详情显示任务，坐席不重复发起。
- 取消资格仍由 `backend/tools/policy.py` 的 Policy Engine 判定；模型只做意图理解。
- 订单归属只按客户 `oms_customer_id`；坐席只按交接单 `verified_order_ids`。

### 3.2 数据模型、一致性与迁移

复用 `cancellation_requests`，新增列（迁移 `0014_order_cancel.py`，只加法，可回滚）：

| 列 | 类型 | 说明 |
|---|---|---|
| `requested_by_type` | `VARCHAR(16) NULL` | `CUSTOMER` / `AGENT`；旧数据回填 `CUSTOMER` |
| `requested_by_id` | `VARCHAR(64) NULL` | 客户 id 或员工 id；旧数据回填 `user_id` |
| `confirmed_at` | `TIMESTAMPTZ NULL` | 客户确认时间；未确认为空 |
| `confirmation_source` | `VARCHAR(16) NULL` | `BUTTON` / `PHRASE` |
| `confirmed_by_id` | `VARCHAR(64) NULL` | 确认的客户 id |

- `user_id` 仍表示订单归属客户；坐席发起时 `user_id=客户`、`requested_by_type=AGENT`。
- 索引：保留 `(tenant_id, idempotency_key)` 唯一；新增部分唯一索引 `uq_cancellation_active_order`（见 3.3）。
- 列表 DTO `CustomerOrderSummary` 不落库：`order_id`、`item_summary`、`order_status`、`status_label`、`amount_cents`、`currency`、`created_at`、`created_at_local`、`cancelable`。`cancelable` 由 OMS 状态派生；003 的消息 `payload` 不变，聊天卡片按 `order_status` 渲染按钮。
- 迁移前若旧数据存在同订单多个活跃任务，先收尾；回滚删新增列与索引。

**一致性与事务边界**

| 操作 | 提交方式 | 不负责 |
|---|---|---|
| 发起/确认/拒绝（客户或坐席） | 请求级 `get_session` 统一提交；路由只 `flush` | 不新开业务 session |
| 任务状态 + 确认卡片消息 + 审计 | 同一请求事务 | OMS 调用不提交数据库 |
| 列表读取 | `get_read_session`，不提交 | 业务写 |
| 启动恢复 | `session_factory()` 独立 session，逐任务复用 `trace_id` | 请求事务 |
| 审计失败 | 返回 503，业务回滚 | 静默丢弃 |
| 工具执行记录 | `BufferedTraceSink` best-effort | 业务事务 |

### 3.3 API / 状态机 / 并发

**客户接口**

| 方法与路径 | 用途 | 事务/授权 |
|---|---|---|
| `GET /customer/orders?limit=5` | 最近订单列表 | 只读 session；本人同租户；未绑定 OMS 返回空 |
| `POST /customer/cancellations` | 发起取消，返回任务与确认卡片 | 写请求 UoW；校验归属与资格 |
| `POST /customer/cancellations/{id}/confirm` | 客户确认；来源 `BUTTON` | 写请求 UoW；校验任务归属/状态/未过期 |
| `POST /customer/cancellations/{id}/decline` | 客户拒绝 | 写请求 UoW；任务转 `ABANDONED` |

聊天里的固定短语在 `customer_chat` 的取消分支处理：找到该客户最近等待确认任务，调用同一确认服务，来源 `PHRASE`。

**工作台接口**

| 方法与路径 | 用途 | 授权 |
|---|---|---|
| `POST /workspace/conversations/{id}/cancellations` | 坐席发起取消并向客户发确认卡片 | 本人接管 + 会话状态 + 订单在 `verified_order_ids` |
| `GET /workspace/conversations/{id}` | 详情增加取消任务摘要 | 本人接管；无 confirm/submit 路由 |

**状态机**

| from | event | guard | to | 副作用 |
|---|---|---|---|---|
| `COLLECTING` | 资格通过 | 归属/状态校验通过 | `AWAITING_CONFIRMATION` | 持久化任务、发确认卡片 |
| `COLLECTING` | 资格不通过 | — | `ELIGIBILITY_REJECTED` | 记录原因，不写 OMS |
| `AWAITING_CONFIRMATION` | 客户确认 | 未过期（默认 24h，可配置） | `SUBMITTING` | 调 `submit_cancel` |
| `AWAITING_CONFIRMATION` | 客户拒绝/超时 | — | `ABANDONED` | 不写 OMS |
| `AWAITING_CONFIRMATION` | 关闭聊天会话 | — | 不变 | 任务保留，订单页可确认 |
| `SUBMITTING` | 提交返回明确状态 | — | `ACCEPTED`/`REJECTED`/`SUBMIT_UNKNOWN` | 持久化结果 |
| `SUBMIT_UNKNOWN` | 恢复查询 | 最多 3 次退避 | `ACCEPTED`/`CANCELLED`/`REJECTED`/`MANUAL_REVIEW` | 不重复提交 |
| `ACCEPTED` | 刷新结果 | 未超恢复上限 | `CANCELLED`/`REJECTED` | 推进终态，刷新到最终结果 |
| 任意终态 | 重复确认/拒绝 | — | 不变 | 幂等返回 |

**并发与幂等**

- 幂等键在任务创建时生成，后续重试复用；`(tenant_id, idempotency_key)` 唯一。
- 部分唯一索引 `(tenant_id, order_id) WHERE state IN ('COLLECTING','AWAITING_CONFIRMATION','SUBMITTING','SUBMIT_UNKNOWN','ACCEPTED')`；并发插入由数据库兜底，冲突时回读已有任务（或 409）。
- 确认用条件更新/版本锁：重复确认幂等返回；并发确认仅一个推进。
- 同一订单只允许一个进行中任务；终态后再次发起按新请求走资格判定。
- 事务与 UoW 归属见 3.2「一致性与事务边界」。

### 3.4 失败路径与用户可见文案

| 场景 | 系统行为 | 客户可见 | 证据 |
|---|---|---|---|
| 可取消订单 | 创建任务，等待确认 | 确认卡片（尚未提交） | AC-60 |
| 备货中/已发货/已送达/已取消 | 资格拒绝，不写 OMS | 不可取消 + 原因 + 可转人工 | AC-64 |
| 订单不存在/他人/跨租户 | 不建任务，不调用 OMS | 统一“查无此单” | AC-65 |
| 资格/列表 OMS 超时或异常 | 不建任务或提示重试；连续 2 次资格失败转人工 | “暂不可用，可重试或转人工” | AC-59、AC-67 |
| 提交超时/非法响应/未知 | 进入结果未知，按幂等键恢复 | “已提交，正在核实受理结果” | AC-67 |
| 恢复耗尽 | 转入人工复核 | “已转人工核实” | AC-68 |
| 确认过期 | 任务结束，不提交 | “未提交，可重新发起” | AC-62 |
| 关闭聊天会话 | 等待确认任务保留，不自动提交/放弃 | 订单页仍可确认 | AC-62 |
| 已受理后 | 按 OMS 结果刷新 | “已取消/被拒绝”或“处理中” | AC-61、AC-67 |
| 重复确认/并发 | 幂等返回当前状态 | 同一结果文案 | AC-66 |
| 审计失败 | 503，业务回滚 | 通用错误，不暴露审计细节 | AC-70 |

结果文案以 `backend/domain/cancellation.py` 的 `render_result` 为唯一出口；本设计不重复整表，只约束“已受理≠已取消、已取消≠已退款”。

### 3.5 测试策略

- unit：资格/状态机/文案/幂等判定；`backend/domain/cancellation.py`、`backend/tools/policy.py`。
- integration：客户列表、发起、确认/拒绝、工作台发起、越权、超时恢复；用种子客户 + Mock OMS。
- contract：列表 DTO/确认/拒绝路由的 OpenAPI 与前端类型。
- e2e：客户列表取消、聊天取消、坐席发起+客户确认三条岗位路径。
- evals：取消成功、资格拒绝、越权、重复、超时恢复、未知转人工场景。
- 故障注入：Mock OMS 的 `timeout`/`unavailable`/`invalid_response`/`lost_response`。

## 4. 备选方案与代价（Alternatives Considered）

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. 复用旧 Workflow + 新接入（本方案） | 状态机、幂等、恢复已有；改动集中在入口与授权 | 需补列表、确认路由、工作台与审计 | 采用 |
| B. 重写取消 Workflow | 可与新模型贴合 | 重复实现、回归风险大 | 不采用 |
| C. 列表复用聊天消息 | 无新接口 | 客户端要维护消息状态、无独立页面 | 不采用 |
| D. 文字确认代替卡片 | 无前端控件 | 易误触、不可判定、无法展示影响 | 不采用 |
| E. 坐席二次提交 | 坐席可控 | 真实平台少见、多一步 | 不采用（淘宝式自动提交） |

- Drawbacks：复用旧 Workflow 要接受 M1-P 的状态名、表与工具契约；列表页与确认路由是新面；M1 不退款，客户可能把“已取消”误解为“已退款”，必须靠文案与文案测试约束。
- Prior art：淘宝【帮他退款】是“客服代发起 + 客户确认 + 系统执行”；京东在线支付订单商家不能代取消，只能客户本人或京东客服操作。本设计取淘宝式，M1 不区分支付方式，生产接入按平台规则限制。

## 5. 跨切面关注点（Cross-cutting Concerns）

### 5.1 安全、权限与审计

越权矩阵见 `requirements.md` 附录 C.1。要点：

- 客户只能访问本人同租户订单/任务；他人/跨租户统一 404。
- 坐席只能对本人接管会话、交接单 `verified_order_ids` 内的订单发起；非本人 404。
- 确认只接受客户会话；坐席调用确认接口 403。
- 审计事件：`cancellation.requested`、`cancellation.confirmed`、`cancellation.abandoned`、`cancellation.submitted`、`cancellation.result`；字段含发起人、确认人、订单、任务、结果、错误码、确认来源；不含 PII 与原幂等键。审计与业务同事务，失败 503。
- 工具调用经 `ToolGateway` 写 `tool_executions`（资格/提交/结果），不含 PII。

| 威胁 | 控制 | 验证 |
|---|---|---|
| 跨客户/跨租户取消 | 服务端归属闸门 + 统一 404 | AC-65 |
| 坐席代确认/无确认提交 | 确认路由仅客户身份；状态机校验；403/409 | AC-65、AC-69 |
| 重复提交/重放 | 幂等键 + 活跃唯一索引 + 版本锁 | AC-66、AC-67 |
| 提示注入诱导取消 | 模型不直接提交；资格/归属在服务端 | AC-63 |
| PII 泄露 | 白名单摘要；审计不含正文/支付信息 | AC-70 |
| 审计篡改 | 只读审计、无双写接口 | AC-70 |

### 5.2 可观测性与测试 seam

| AC | 事实/契约 | 测试 seam |
|---|---|---|
| AC-59 | 订单列表只返回本人摘要；访问审计 5 分钟去重 | `GET /customer/orders` + `audit_view` 去重 + Trace |
| AC-60 | 按钮仅可取消时出现；创建任务 | 列表/聊天卡片 + 发起路由 |
| AC-61 | 客户确认后只提交一次 | confirm 路由 + Workflow + Mock OMS |
| AC-62 | 拒绝/过期结束；关闭聊天保留任务 | decline/超时/关闭流程 |
| AC-63 | 聊天取消分流与候选 | `customer_chat` 取消分支 |
| AC-64 | 资格原因与零写 | Policy + Mock 订单状态 |
| AC-65 | 越权矩阵 | 归属闸门/工作台授权 |
| AC-66 | 重复/并发只一次 | 幂等键/唯一索引/条件更新 |
| AC-67 | 未知恢复与收敛 | Mock faults + 恢复器 |
| AC-68 | 交接单取消上下文 | 交接单 `context` + 工作台 DTO |
| AC-69 | 坐席发起、客户确认、自动提交 | 工作台发起 + 客户确认 |
| AC-70 | 审计/工具记录/链路 | 审计表 + `tool_executions` + Trace |
| AC-71 | 列表/卡片/工作台四态与可访问性 | 前端组件测试 |
| AC-72 | 岗位走查与评测 | `evals/` + 走查记录 |

### 5.3 兼容、迁移与发布/回滚

- 发布：`M1_ENABLED` 控制新页面/新路由；旧取消 API 不再暴露。
- 迁移：`0014_order_cancel.py` 只加法；回滚删列/索引。
- 兼容性：003 的消息 `payload` 不变；列表 DTO 新增字段只影响新页面；旧任务 `requested_by_*` 为空时按客户发起处理。
- 回滚行为：隐藏“我的订单”入口、取消意图恢复转人工；保留任务表与历史记录。
- 监控：`cancel_total{state}`、`cancel_submit_latency_ms`、`cancel_unknown_total`；异常时看 `trace_id`。

### 5.4 性能、容量与成本

- 列表 ≤5 条，单次 OMS 查询（≤2s 超时），不叠加模型调用。
- 取消提交 P95 ≤3s（Mock ≤500ms）。
- 不新增连接池；确认/提交在请求事务内完成。
- 成本：列表/确认不新增外部付费调用；取消提交只多一次 OMS 写与一次结果查询。

## 6. 未决问题（Open Questions）

已定决策（2026-11-21）：

- Q-1：确认有效期改为 24 小时（可配置）。
- Q-2：关闭聊天会话不结束等待确认任务，客户仍可在订单页确认。
- Q-3：已受理后继续推进到最终结果，Mock 可注入受理后取消成功/被拒绝。
- Q-4：卡片按钮为主，固定短语辅助，并在聊天里提示可回复短语。
- Q-5：列表读取审计复用 `audit_view` 的 5 分钟去重（同一客户/列表/动作），每次请求仍写 Trace/metrics。
- Q-6：M1 不区分支付方式，统一淘宝式；生产接入按 OMS/平台规则限制，写入假设与回滚说明。
- Q-7：人工接管期间客户仍可在订单页自助取消；工作台显示该任务，坐席不重复发起，同一订单活跃任务唯一约束兜底。

无未决问题。
