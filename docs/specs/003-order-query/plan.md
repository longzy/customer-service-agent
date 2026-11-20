# 订单查询 plan

> 结构依据：Google Design Doc（Context / Goals / Design / Alternatives / Cross-cutting）。
> 状态：草案（Frame 阶段随 brief 一起评审；批准前不得进入 Build）。

- 状态：草案
- 日期：2026-11-20
- 风险级别：T3
- 依据：`brief.md`、[总体架构 4.3 订单访问](../../architecture/overview.md)、[ADR-0006](../../adr/0006-customer-login.md)、[ADR-0011](../../adr/0011-model-failure-degradation.md)

## 1. 背景与范围（Context and Scope）

001 已把客户登录、会话、AI 回复、转人工、队列、接管、回复、关闭/转回、审计与限速做完；002 完成了两个前端的视觉与组件规范。001 明确把订单查询排除在外（brief 非目标），并把交接单 `order_count` 固定为 0（AC-32/35），待本切片重审。

现有可复用的基座：

- `backend/adapters/oms/port.py` 的 `OmsPort`：`get_order` / `list_recent_orders` / `submit_cancel`，归属按 `(tenant_id, user_id)`；`MockOmsAdapter` 夹具已按 `user-a1` / `user-b1` 归属。
- `backend/tools/gateway.py` 的 `ToolGateway`：契约 JSON Schema 校验、身份字段剥离、归属闸门、2s 超时、错误归一、审计与 Trace。
- `backend/platform/observability.py` 的 `tool_executions`（started/rejected/result）与 `TraceView`。
- `backend/conversations/handoffs.py` 的交接单 `context` JSON 字段（当前 `order_count` 写死 0）。
- `backend/agent_runtime/model.py` 的 `ChatReply`（intent/confidence/reply），模型只做意图分类，不接触订单数据。

本切片把"客户问订单 → 查 OMS → 回答 → 交接单/工作台可见"接回 AI_ACTIVE 会话，不改会话状态机。

## 2. 目标与非目标（Goals and Non-Goals）

### Goals

- 客户在聊天里查本人订单（单笔/最近），AI 回复只含 OMS 事实。
- 订单归属在服务端强制：跨客户/跨租户统一"查无此单"，与不存在不可区分。
- 交接单带最近订单摘要与 `order_count`；坐席工作台详情可见。
- 订单查询有审计与 Tool Trace；失败分级与 F-24 一致，不误建单。
- 客户侧订单卡片与工作台订单区符合 002 设计系统（ui-spec 增补）。

### Non-Goals

- 取消/退款/物流轨迹/订单修改（004、M2）。
- 代客查单、跨账号、主管视角订单检索。
- 真实 OMS 接入与线上联调（M5）；本切片只保证端口契约。
- 模型自主 function calling 与多轮工具编排（M3+ 再评估）。
- 订单列表分页、历史订单搜索、推荐。

## 3. 方案（The Design）

### 3.1 总体方案与模块边界

```
客户消息（AI_ACTIVE）
  -> 关键词/意图分类（现有 ChatModel.respond；ORDER 意图）
  -> 订单分支：构造 OmsAccess(tenant_id, user_id=oms_customer_id)
       -> ToolGateway.invoke("get_order", {order_id}) 或
          invoke("list_recent_orders", {limit: 5})
       -> 订单摘要（白名单字段）
       -> 确定性回复模板（中文） + 订单快照 payload
  -> 消息落库（customer/ai）+ AI 事件（order_query）
  -> 需要转人工时：交接单 context 写 orders/order_count
```

关键决策：

1. **模型不直接调工具**：模型只输出意图与订单号候选（现有 `emit_intent`），订单查询由服务端在 `AI_ACTIVE` 分支确定性执行。这样越权在服务端闸门被挡住，模型永远看不到未授权订单，提示注入无法扩大数据面。备选（function calling）见第 4 节。
2. **回复用确定性模板**：订单摘要按固定句式拼装（订单号、商品、状态文案、金额、下单时间），不让模型改写。AC-54 的事实性因此可 100% 保证，测试也稳定。M3 若需要更自然措辞，再引入"带摘要的二次模型调用"。
3. **Gateway 复用**：`ToolGateway` 是同步实现（ThreadPoolExecutor + 2s 超时），在 async 路由里用 `asyncio.to_thread` 调用；`Identity` 由客户会话构造（`account_id=customer.id`、`user_id=customer.oms_customer_id`、`tenant_id`、显示名）。
4. **订单快照存消息**：`service_messages.payload` JSONB 存最多 5 条摘要，前端按消息渲染卡片；刷新/重放不重新查 OMS。卡片标注"查询时状态"，避免 OMS 状态变化后的误解。
5. **交接单上下文**：`ServiceHandoff.context` 已有 JSON 字段，写入 `orders`（≤5 条摘要）与 `order_count`；不新增列。转人工发生在订单查询之后（AI 判断需要人）时带上本次查询结果；客户直接说"转人工"时，若本会话已有成功查询快照则复用，否则查一次最近订单（失败不阻塞转人工）。

### 3.2 数据模型与迁移

迁移 `0013_order_query.py`（只加法，可回滚）：

| 表 | 变更 | 说明 |
|---|---|---|
| `service_customers` | `oms_customer_id VARCHAR(64) NULL`；部分唯一索引 `(tenant_id, oms_customer_id) WHERE oms_customer_id IS NOT NULL` | 客户账号 ↔ OMS 客户身份；生产由账号绑定流程填，M1 种子回填 `customer_a→user-a1`、`customer_b→user-b1` |
| `service_messages` | `payload JSONB NULL` | AI 消息的订单摘要快照（≤5 条）；客户消息为 NULL |

- 回填：`scripts/seed_demo.py` 写入 `oms_customer_id`；`scripts/reset_dev_db.py`/迁移不猜测生产数据。
- 未绑定 `oms_customer_id` 的客户：所有订单查询返回"查无此单"（不报错、不泄露），并记 warning 指标 `order_query_unbound_total`；不阻塞聊天。
- 订单摘要白名单字段：`order_id`、`item_summary`、`order_status`、`amount_cents`、`currency`、`created_at`。`items`、`paid_at`、`shipped_at` 不进快照。

### 3.3 API / 状态机 / 并发

- **不新增客户 HTTP 路由**：查询发生在 `POST /conversations/{id}/messages` 的同一次调用内；响应消息带 `payload`，现有 3s 轮询自动带出。
- **工作台 DTO**：`ConversationDetail`（或现有详情响应）增加 `orders: [{...}]` 与 `order_count`；值来自交接单 `context`，不实时查 OMS（避免坐席每次打开都打 OMS）。OMS 异常只在客户查询时暴露。
- **状态机**：不变。订单查询成功/查无/失败都不改 `conversations.status`；只有连续失败转人工走现有 `_queue_for_handoff`。
- **并发**：同一会话的消息处理已有串行语义（001）；订单查询在业务事务外（`asyncio.to_thread`），完成后在同一事务写消息与事件；Gateway 超时 2s，总响应时间受 `MODEL_TIMEOUT` 与 2s 上限约束。
- **幂等**：消息幂等键重放直接返回已存消息与 `payload`，不重新查 OMS；订单查询失败的重试是客户的新消息，按新请求处理。
- **顺序**：先在 AI_ACTIVE 分支完成意图分类，再查询，再落库；关键词转人工优先（现有逻辑不变）。

### 3.4 失败路径与用户可见文案

| 场景 | 行为 | 客户可见文案 |
|---|---|---|
| 订单不存在 / 他人订单 / 未绑定 OMS 身份 | 不建单、不泄露差异；AI 事件 `order_query`/`not_found` | "没有查到你名下的这笔订单，请核对订单号，或说「转人工」。" |
| 无任何订单 | 不建单 | "你名下暂时没有订单。需要的话可以说「转人工」。" |
| 多个订单号 | 不调用 OMS；澄清 | "你提到了多个订单号，请一次查一笔，例如 ORD-10001。" |
| 半截/格式错误 | 不调用 OMS；澄清 | "订单号看起来不完整，请发完整的订单号，例如 ORD-10001。" |
| OMS 超时/异常/非法响应 | 不建单；`order_failure_count += 1`；AI 事件 `timeout/error` | "订单查询暂时不可用，可以重试，或说「转人工」。" |
| 同会话连续 2 次订单失败 | 转人工，`trigger=order_query_failure`，交接单带 `failure_count` | "订单查询连续失败，已为你转接人工。" |
| 模型分类失败 | 走 F-24 既有路径，不影响订单计数 | 沿用 AC-31 文案 |

- `order_failure_count` 只统计订单查询失败，不并入模型失败计数（AC-53）；任一成功查询清零。
- 订单失败不写审计失败语义（审计只在查询成功/查无/失败各记一条 `order.queried`，见 5.1）。

### 3.5 前端

**客户侧（apps/chat）**

- `MessageList` 的 AI 消息若 `payload.orders` 非空，渲染订单卡片：订单号（等宽）、商品、状态 chip、金额、下单时间；最多 5 张，超出折叠为"查看全部"（M1 先不做分页，只显示 5 条）。
- 状态文案映射集中在 `features/chat/lib/orderStatus.ts`；颜色只用于状态 chip 的圆点/文字，不使用大色块。
- 空/错误：订单查询失败时 AI 文本已给出下一步；卡片不渲染。加载态不单独做（消息随轮询到达）。
- 可访问性：卡片为 `article` + 标题层级；订单号可选中复制；`aria-live` 由消息区统一承担。

**坐席侧（apps/workspace）**

- 会话详情新增"订单"区：最近 ≤5 条，字段同客户侧；空态"该客户名下暂无订单"；OMS 异常时显示"订单信息暂不可用"（详情数据来自交接单快照，正常不会实时失败）。
- 队列详情抽屉的"订单"指标改为真实 `order_count`（当前恒 0）。

**设计系统**：`ui-spec` 增补订单卡片契约（3.x 新小节）与状态色规则；组件放 `apps/chat/components/ui/OrderCard.tsx`，workspace 复制一份（沿用 frontend.md 的"允许组件重复、不建共享包"决策）。

### 3.6 可观测与评测

- **Tool Trace**：沿用 `ToolGateway` 写入 `tool_executions`（started/result/rejected）；`tool_name` 为 `get_order` / `list_recent_orders`，`order_id`、`user_id`、`latency_ms`、`error_code` 已有。
- **审计**：新增事件 `order.queried`（actor=customer，entity=order，metadata：`conversation_id`、`order_id`（可空）、`order_count`、`result`、`error_code`）；`AUDIT_METADATA_KEYS` 增加 `order_id`、`order_count`、`result`、`tool`。审计与消息同事务，失败按既有 503 回滚。
- **AI 事件**：`service_ai_events` 写 `event_type=order_query`、`name=get_order|list_recent_orders`、`status=ok|not_found|timeout|error`、`order_id`（如有）。
- **评测**：`evals/` 新增订单查询场景（最近订单、指定订单、他人订单、不存在、多单澄清、OMS 超时）；断言回复中的订单号/金额/状态与夹具一致、无夹具外订单号。
- **指标**：`order_query_total{tool,status}`、`order_query_latency_ms`、`order_query_unbound_total`。

### 3.7 测试 seam

- 集成：`tests/integration/test_order_query_AC_50.py` ~ `test_order_query_AC_57.py`，用种子客户 + Mock OMS 夹具；跨客户用 customer_a/customer_b。
- 前端：`apps/chat/tests/OrderCard.test.tsx`、`apps/workspace/tests/ConversationOrders.test.tsx`。
- 契约：`packages/contracts/tools/get_order.json` / `list_recent_orders.json` 不变；若需新增字段，先改契约再生成前端类型。
- 迁移：`tests/integration/test_migrations.py` 加 0013 升级/回滚。

## 4. 备选方案（Alternatives Considered）

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| A. 服务端确定性查询 + 模板回复（本方案） | 越权不可绕过；事实性 100%；测试稳定；改动小 | 回复措辞固定，不够自然 | M1 采用 |
| B. 模型自主 function calling（多轮 tools） | 更"Agent"，可组合多工具 | 权限校验、超时、成本、可观测复杂度高；模型可被注入诱导调用；FakeModel 与评测成本大 | M3+ 再评估 |
| C. 二次模型调用生成措辞（摘要作为上下文） | 回复自然，事实性可评测 | 每次订单查询两次模型调用，成本翻倍；仍可能改写错误 | M3 若需要自然度再评估 |
| D. 固定话术不查 OMS（现状的"安慰话术"） | 零成本 | 答非所问，客户仍需转人工 | 否 |

## 5. 跨切面关注点（Cross-cutting Concerns）

### 5.1 安全、权限与审计

- **归属**：`OmsAccess.user_id` 只取当前客户 `oms_customer_id`，请求体不得携带身份/订单归属字段（Gateway 的 `has_identity_fields` 已强制）。
- **不可区分**：`OrderNotFound`、他人订单、未绑定统一同一文案与同一 AI 事件状态；HTTP 层不新增可枚举接口。
- **最小化**：只取白名单摘要字段；不把 `items`、手机号、支付信息写入消息 payload、交接单、审计或日志。
- **审计**：`order.queried` 与消息同事务；审计失败 503 回滚（沿用 001/ADR-0012）；订单号在审计中是标识，不是 PII。
- **限速**：沿用客户消息限速；不新增独立订单查询限速（查询只能通过发消息触发）。
- **权限**：工作台订单区只读；第二坐席仍 404（001 既有）；不新增坐席跨客户查询接口。

### 5.2 可观测性与测试 seam

- Trace：`tool_executions` 已含 `trace_id`；`TraceView` 能按 `trace_id` 串起消息、工具、审计。
- 日志：只记 `conversation_id`、`order_id`、`tool`、`status`、`latency_ms`；不记订单内容。
- 测试 seam：`MockOmsAdapter.faults` 注入超时/不可用/非法响应；`/_admin/faults` 仅非生产挂载（既有）。

### 5.3 风险、回滚与发布

- 风险：订单快照与 OMS 实时状态不一致 → 卡片标注"查询时状态"；OMS 慢 → 2s 超时 + 提示；旧测试断言 `order_count=0`/问订单转人工 → 随本切片同步修订（AC-31/32）。
- 发布：`M1_ENABLED` 控制；迁移 0013 只加法；种子回填 `oms_customer_id`。
- 回滚：回滚代码到 001 收口版本；保留 `payload` 与 `oms_customer_id` 列（不影响旧逻辑），恢复"问订单转人工、`order_count=0`"的行为。

### 5.4 性能

- 订单查询单次 OMS 调用（≤2s 超时），不叠加模型调用（模型分类已在消息路径中）。
- 最近订单最多 5 条，摘要字段小；消息 payload ≤ 数 KB。
- 不因订单查询新增数据库连接占用：Gateway 调用在业务连接之外，完成后统一写消息/事件/审计。

## 6. 未决问题（Open Questions）

1. `order_count` 口径：本切片取"最近订单条数（≤5）"还是"本人订单总数"？取总数需要 `OmsPort` 新增计数方法或返回 total。当前建议先取"最近 ≤5"，在 DTO 注释与文案中写清"最近订单"。
2. 订单卡片是否需要"状态可能已更新"的显式提示？当前建议卡片页脚标注"查询时状态"。
3. 生产环境 `oms_customer_id` 的绑定流程（谁在何时写入）不在 M1 范围；M1 只保证种子回填与空值安全降级。
4. 是否需要在 `ConversationDetail` 中实时刷新订单（打开详情时重新查 OMS）？当前建议不查，避免坐席侧放大 OMS 调用；004 取消时再评估。
