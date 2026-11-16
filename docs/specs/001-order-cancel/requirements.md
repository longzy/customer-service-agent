# M1 需求：订单查询与未发货订单取消

- 状态：已批准
- 批准：2026-11-15（用户确认，含测试账号登录页与 AC-20）；2026-11-16 澄清确认（判定表与 T-11 结果文案）
- 变更说明：2026-11-14 按 Spec 开发规范重写为 EARS 与用户故事结构，补成功标准、关键实体与假设；2026-11-15 增加 US-00 建立会话、FR-11 与 AC-20；2026-11-16 增加 AC-21 会话安全基线（T-20）；同日为 AC-05、AC-09、AC-10、AC-19 补判定表（澄清，不改行为）；同日为 T-11 明确 AC-10、AC-11、AC-16 判定表与结果文案唯一出口。
- 渠道：Web Chat
- 业务系统：Mock OMS
- 关联架构：`docs/architecture/overview.md`

## 1. 目标

让已认证用户能够查询本人订单，并在订单允许时，经明确确认后安全取消未发货订单。

## 2. 用户故事与验收场景

优先级说明：P1 构成最小可用闭环，P2 为体验补强。每个故事都能独立测试，不依赖其他故事先完成。

### US-00 建立会话（P1）

作为开发期使用者，我可以选择一个测试账号进入系统，以便验证不同租户与用户下的行为。

- 优先级：P1（后续所有演示的起点）
- 独立测试：打开未登录页面，选择任一测试账号，断言会话建立且租户与用户正确。
- 验收场景：
  1. Given 未登录访问 When 选择测试账号 Then 建立会话并绑定该账号的租户与用户（AC-20）
  2. Given 已登录 When 切换为另一租户的账号 Then 会话更新且后续请求按新租户授权（AC-20）

### US-01 查询订单（P1）

- 优先级：P1
作为已认证用户，我可以用订单号查询本人订单，以便确认订单状态。

- 独立测试：给定夹具订单，直接调用查询接口即可验证，不依赖取消流程。
- 验收场景：
  1. Given 已认证用户与本人的未发货订单 When 按订单号查询 Then 返回正确订单且无任何写操作（AC-01）
  2. Given 已认证用户 When 查询他人订单号 Then 返回统一“查无此单”且不调用 OMS（AC-02）
  3. Given 用户属于租户 A When 访问租户 B 的订单 Then 服务端拒绝（AC-03）
  4. Given 请求携带未知字段或非法类型 When 到达网关 Then 被拒绝且无业务副作用（AC-14）

### US-02 查看最近订单（P2）

- 优先级：P2
作为忘记订单号的用户，我可以查看自己有权限访问的最近订单。

- 独立测试：给定每个租户的夹具订单，调用最近订单接口即可验证。
- 验收场景：
  1. Given 已认证用户 When 请求最近订单 Then 只返回本人可见的有限数量订单（AC-01）

### US-03 取消符合条件的订单（P1）

- 优先级：P1
作为订单尚未发货的用户，我可以请求取消；系统说明影响并在我确认后提交。

- 独立测试：给定可取消订单，走完“请求取消 → 确认 → 提交”闭环即可验证，不依赖查询的故事。
- 验收场景：
  1. Given 可取消订单 When 用户请求取消 Then 展示订单与影响并停在等待确认（AC-04）
  2. Given 处于等待确认 When 用户明确确认 Then 只提交一次且可追踪到已受理或已取消（AC-05）
  3. Given 处于等待确认 When 用户拒绝或未确认 Then 不产生取消请求（AC-06）
  4. Given 处于等待确认 When 用户放弃或确认超时 Then 任务转已放弃且无 OMS 写调用（AC-19）

### US-04 解释不可取消原因（P2）

- 优先级：P2
作为用户，如果订单不符合取消条件，我希望知道原因和下一步。

- 独立测试：给定已发货订单，请求取消即可验证原因码与零写调用。
- 验收场景：
  1. Given 已发货订单 When 用户请求取消 Then 返回不可取消原因且 OMS 写调用为 0（AC-07）

### US-05 安全重试（P1）

- 优先级：P1
作为用户，当网络或接口异常时，我希望系统确认取消是否已受理，而不是重复创建申请。

- 独立测试：注入超时、重复响应与格式错误，观察幂等键与最终状态即可验证。
- 验收场景：
  1. Given 用户重复点击或网络重试 When 请求到达 Then 只产生一条取消申请（AC-09）
  2. Given 写接口超时但 OMS 已受理 When 系统查询状态 Then 恢复为受理且不重复提交（AC-10）
  3. Given OMS 返回格式错误 When 系统解析 Then 归类为未知，不猜测成功（AC-11）
  4. Given OMS 连续不可用 When 重试耗尽 Then 转入人工复核（AC-12）

### US-06 人工接管（P2）

- 优先级：P2
作为用户，当系统无法确认状态时，我希望问题被转给人工且无需重复描述。

- 独立测试：在任意状态请求人工，检查转接上下文即可验证。
- 验收场景：
  1. Given 任意会话状态 When 用户要求人工 Then 转接且携带完整任务上下文（AC-13）

### 边界情况

以下情况必须有确定结果，全部对应验收用例：

- 订单号格式非法、不存在或属于他人（AC-02）
- 同时存在多个候选订单，无法唯一定位（AC-08）
- 订单已发货或已送达（AC-07）
- 重复提交与网络重试（AC-09）
- 写请求超时但后端已成功（AC-10）
- 下游返回非法格式（AC-11）
- 下游长时间不可用（AC-12）
- 用户确认超时或主动放弃（AC-19）
- Tool 参数包含未知字段或非法类型（AC-14）
- 提示词诱导跨租户访问（AC-15）

## 3. 功能需求

采用 EARS 句式，以便每条需求可以直接转成测试用例。

### FR-01 身份与权限

- WHEN 请求到达 THE SYSTEM SHALL 从可信认证上下文获取租户与用户身份。
- IF 请求体携带 `tenant_id` 或 `user_id` THEN THE SYSTEM SHALL 忽略并以认证上下文为准。
- WHEN 用户查询订单 THE SYSTEM SHALL 只返回该用户有权访问的订单。
- IF 订单不属于当前用户或租户 THEN THE SYSTEM SHALL 返回统一 `NOT_FOUND_OR_UNAUTHORIZED`，不泄露订单是否存在。
- IF Tool 输入包含未知字段或非法类型 THEN THE SYSTEM SHALL 在网关拒绝且不产生业务副作用。

### FR-02 订单查询

- WHEN 用户提供订单号 THE SYSTEM SHALL 返回该订单的摘要。
- WHEN 用户未提供订单号 THE SYSTEM SHALL 返回该用户可见的有限数量最近订单。
- THE SYSTEM SHALL 在订单摘要中包含订单号、商品摘要、订单状态、可取消性与金额。

### FR-03 歧义处理

- WHEN 用户提供的信息无法唯一定位订单 THE SYSTEM SHALL 提出澄清问题。
- WHILE 尚未完成澄清 THE SYSTEM SHALL 不发起任何写操作。

### FR-04 取消资格

- THE SYSTEM SHALL 由服务端 Policy Engine 唯一判定取消资格。
- WHEN 订单存在、属于当前用户、未发货且未取消 THE SYSTEM SHALL 判定为可取消。
- IF 订单已发货、已送达、已取消或不属于当前用户 THEN THE SYSTEM SHALL 返回不可取消与原因码。
- THE SYSTEM SHALL 不接受 Agent 对资格结果的覆盖或弱化。

### FR-05 明确确认

- WHEN 用户表达取消意图 THE SYSTEM SHALL 展示订单信息与取消影响。
- WHEN 用户通过界面确认控件明确确认 THE SYSTEM SHALL 只提交一次。
- IF 用户拒绝、改主意或未确认 THEN THE SYSTEM SHALL 不提交。
- IF 确认阶段超时或用户放弃 THEN THE SYSTEM SHALL 将任务置为已放弃且不调用 OMS 写接口。

### FR-06 幂等提交

- THE SYSTEM SHALL 为每次待执行的取消生成稳定幂等键。
- WHEN 同一幂等键的请求重复到达 THE SYSTEM SHALL 返回同一业务结果且不新建申请。

### FR-07 状态查询与恢复

- WHEN 写接口超时 THE SYSTEM SHALL 使用原幂等键查询状态。
- WHILE 结果未知 THE SYSTEM SHALL 不假设成功或失败。
- IF 重试耗尽仍未知 THEN THE SYSTEM SHALL 转入 `MANUAL_REVIEW`。

### FR-08 结果表达

- THE SYSTEM SHALL 区分“已提交”“已受理”“已取消”“拒绝”和“未知”五种表达。
- IF 状态为 `ACCEPTED` THEN THE SYSTEM SHALL 不将其表述为已取消。

### FR-09 审计与 Trace

- THE SYSTEM SHALL 将对话、意图、Tool 调用、确认、状态转换与业务结果关联到同一 `trace_id`。
- THE SYSTEM SHALL 在审计记录中包含操作主体、租户、订单、幂等键摘要、结果与错误分类。

### FR-10 人工接管

- WHEN 用户要求人工 THE SYSTEM SHALL 转接。
- IF 权限异常、结果未知且重试耗尽、或业务系统不可用 THEN THE SYSTEM SHALL 提供转人工路径。
- THE SYSTEM SHALL 在转接上下文中包含对话摘要、已查询订单、当前 Workflow 状态与待处理步骤。

### FR-11 会话建立

- WHEN 用户选择测试账号 THE SYSTEM SHALL 建立会话并将租户与用户绑定到该会话。
- WHEN 用户退出或切换账号 THE SYSTEM SHALL 结束旧会话并建立新会话。
- THE SYSTEM SHALL 只在开发期提供测试账号登录，不实现注册、密码与第三方登录。
- IF 请求未携带有效会话 THEN THE SYSTEM SHALL 返回未认证并引导到登录页。

## 4. 非功能需求

- 安全：服务端授权、最小权限、敏感信息脱敏。
- 一致性：业务状态以 OMS 与持久化 Workflow 记录为准。
- 可靠性：所有外部调用有超时、有限重试和结果查询机制。
- 可测试性：模拟 OMS 支持故障注入。
- 可观测性：关键步骤产生结构化 Trace 和审计事件。
- 可评估性：每个需求至少对应一个验收用例。

## 5. 成功标准

与技术实现无关，可按 `requirements.md` 第 10 节 的场景度量：

- **SC-001** 未授权的成功查询次数为 0。
- **SC-002** 重复取消申请数量为 0。
- **SC-003** 不可取消订单的 OMS 写调用次数为 0。
- **SC-004** 注入“后端已成功但响应丢失”时，重复提交为 0 且状态可解释。
- **SC-005** 全部验收用例通过率 100%，且在每次 Prompt、模型或 Tool 变更后全量重跑。

## 6. 关键实体

描述业务含义，不限定实现：

- **订单（Order）**：订单号、商品明细、订单状态、金额、支付与发货时间、归属的租户与用户。
- **取消申请（CancellationRequest）**：所属订单、取消状态、幂等键、最近错误码、创建与更新时间。
- **取消资格结果（EligibilityResult）**：是否可取消、原因码、是否需要用户确认。
- **会话（Conversation）与消息（Message）**：一次对话及其消息，含角色与 `trace_id`。
- **Tool 执行记录（ToolExecution）**：工具名、输入摘要、结果状态、耗时、错误码。
- **审计事件（AuditEvent）**：操作主体、事件类型、关联实体、脱敏后的元数据。

## 7. 假设与依赖

- Mock OMS 是 M1 唯一的业务系统，真实系统在契约稳定后接入。
- M1 只有 Web Chat 一个入口，不接第三方渠道。
- 开发期提供测试账号选择页与会话 Cookie 登录；不实现注册、密码、找回密码与第三方登录。
- 存在两个租户、每租户两个用户，用于跨租户与越权用例。
- 金额以整数分传输，时间以带 `Z` 的 ISO 8601 UTC 字符串传输。
- 不引入重量级工作流平台，Workflow 为数据库持久化的显式状态机。

## 8. 暂不包含

- 退款申请与退款到账。
- 已发货订单拦截与拒收流程。
- 改地址、换货和补发。
- 真实 OMS、支付或物流系统。
- 商品知识和售前推荐。
- 第三方渠道。

## 9. 业务状态定义

### 订单状态（Mock OMS）

- `PAID_UNFULFILLED`：已支付、未发货，可进入取消判断。
- `FULFILLING`：备货/履约处理中，M1 默认不可取消。
- `SHIPPED`：已发货，M1 不可取消。
- `DELIVERED`：已送达，M1 不可取消。
- `CANCELLED`：已取消。

### 取消任务状态

- `COLLECTING`：正在确认订单和信息。
- `AWAITING_CONFIRMATION`：等待用户明确确认。
- `ELIGIBILITY_REJECTED`：不符合条件，禁止提交。
- `SUBMITTING`：正在提交取消申请。
- `SUBMIT_UNKNOWN`：提交结果未知，需要查询。
- `ACCEPTED`：OMS 已受理，但尚未确认最终取消。
- `CANCELLED`：OMS 已确认订单取消。
- `REJECTED`：OMS 拒绝取消。
- `MANUAL_REVIEW`：超出自动处理边界。
- `ABANDONED`：确认阶段超时或用户放弃，未提交，无 OMS 写调用。

### 内部状态与用户可见表达

同一状态只能有一种对外表达；Agent 不得自行创造表达，也不得把内部状态直接暴露给用户。

| 内部状态 | 用户可见表达 |
|---|---|
| `COLLECTING` | 正在确认订单信息 |
| `AWAITING_CONFIRMATION` | 等待您确认 |
| `ELIGIBILITY_REJECTED` | 不可取消，并说明原因 |
| `SUBMITTING` | 正在提交取消申请 |
| `SUBMIT_UNKNOWN` | 已提交，正在核实受理结果 |
| `ACCEPTED` | 已受理，等待最终取消结果 |
| `CANCELLED` | 已取消 |
| `REJECTED` | 取消申请被拒绝 |
| `MANUAL_REVIEW` | 已转人工处理 |
| `ABANDONED` | 未提交（已放弃） |

### 结果回复模板（T-11）

“最终回复”是发送给用户的完整结果句，不等同于界面标签。完整回复由“状态标签 + 原因（仅不可取消）+ 下一步”组成；任何与模板不一致的草稿都替换为模板，不保留草稿措辞。

| 内部状态 | 完整回复模板 | 不得出现 |
|---|---|---|
| COLLECTING | 正在确认订单信息。请稍候。 | 已受理、已取消、已退款、成功 |
| AWAITING_CONFIRMATION | 等待您确认。请在确认卡片中选择“确认取消”或“不取消”。 | 已受理、已取消、已退款、成功 |
| ELIGIBILITY_REJECTED | 不可取消，并说明原因：{原因}。如需进一步处理，可转人工。 | 已受理、已提交、已退款、取消成功 |
| SUBMITTING | 正在提交取消申请。请稍候，无需重复提交。 | 已提交、已受理、已取消、已退款、成功 |
| SUBMIT_UNKNOWN | 已提交，正在核实受理结果。如长时间没有结果，可转人工核实。 | 已受理、已取消、已退款、成功、失败、被拒绝 |
| ACCEPTED | 已受理，等待最终取消结果。如需帮助，可转人工。 | 已取消、已退款、取消成功 |
| CANCELLED | 已取消。如需帮助，可转人工。 | 已退款、退款成功、已到账 |
| REJECTED | 取消申请被拒绝。如需帮助，可转人工。 | 已受理、已取消、已退款 |
| MANUAL_REVIEW | 已转人工处理。人工会尽快核实，请稍候。 | 已受理、已取消、已退款 |
| ABANDONED | 未提交（已放弃）。如仍需取消，可重新发起。 | 已提交、已受理、已取消、已退款 |

原因文案只用于 ELIGIBILITY_REJECTED，原因码由 Policy Engine 给出，Agent 不得改写：

| reason_code | 用户可见原因 |
|---|---|
| UNFULFILLED | 订单未发货 |
| FULFILLING | 订单正在备货 |
| SHIPPED | 订单已发货 |
| DELIVERED | 订单已送达 |
| CANCELLED | 订单已取消 |

- ELIGIBILITY_REJECTED 缺少原因码时不得输出半截“不可取消”文案，按程序错误处理；其他状态即使携带原因码也不展示。
- “不得出现”按子串判定，模板本身不得包含这些子串；原因文案中的“订单已取消”描述订单状态，不视为宣称取消申请成功。
- 确认卡片上的“已支付金额原路退回”是规则说明，不是结果回复，不受“不得声称已退款”约束；结果回复不得出现“已退款”“退款成功”“已到账”。
- 五种结果与状态的对应（分类名，不要求逐字出现）：已提交 = SUBMITTING；已受理 = ACCEPTED；已取消 = CANCELLED；拒绝 = ELIGIBILITY_REJECTED 或 REJECTED；未知 = SUBMIT_UNKNOWN。
- “已提交”是阶段分类，不是 `SUBMITTING` 的逐字文案；`SUBMITTING` 只能说“正在提交取消申请”，不得写成完成态；`SUBMIT_UNKNOWN` 的文案是“已提交，正在核实受理结果”，归“未知”类。
- COLLECTING、AWAITING_CONFIRMATION、MANUAL_REVIEW、ABANDONED 不在五类中，但同样有且只有一条模板；MANUAL_REVIEW 是重试耗尽后的确定状态，不得与“未知”混用。
- ELIGIBILITY_REJECTED 的标签沿用第 9 节表达表的“不可取消，并说明原因”，原因由 `reason_text` 单独展示；标签文案的精简不在 T-11 范围。

## 10. 验收用例

每条验收用例标注其关联的功能需求；实现任务必须引用对应 `AC-*` 标识。判定原则、场景与指标见下文。

### 1. 判定原则

- 验收结果以 Tool、Workflow、Mock OMS 和审计 Trace 为证据。
- 模型回复正确但业务操作错误，判定失败。
- 业务操作正确但用户回复误报状态，判定失败。
- 所有场景必须使用固定测试夹具，禁止依赖真实用户数据。

### 2. 场景

| ID | 场景 | 预期结果 | 关联 FR |
|---|---|---|---|
| AC-01 | 已认证用户查询本人未发货订单 | 返回正确订单；无写操作 | FR-02 |
| AC-02 | 用户查询其他用户订单号 | 不泄露订单数据；记录拒绝审计；不调用 OMS，统一返回“查无此单” | FR-01、FR-02 |
| AC-03 | 用户跨租户访问订单 | 服务端拒绝；Agent 无法通过参数覆盖租户 | FR-01 |
| AC-04 | 用户请求取消未发货订单 | 先说明订单与影响，进入 `AWAITING_CONFIRMATION` | FR-04、FR-05 |
| AC-05 | 用户明确确认 | 只提交一次；状态最终可追踪到 `ACCEPTED` 或 `CANCELLED` | FR-05、FR-06 |
| AC-06 | 用户拒绝或未确认 | 不产生取消请求 | FR-05 |
| AC-07 | 订单已发货 | 返回不可取消原因；OMS 写接口调用次数为 0 | FR-04 |
| AC-08 | 用户提供歧义订单信息 | 请求澄清；确认前不写操作 | FR-03 |
| AC-09 | UI 或网络重复提交 | 相同幂等键；只产生一个取消申请 | FR-06 |
| AC-10 | 写接口超时，但 OMS 实际已受理 | Workflow 进入未知，查询后恢复为受理状态；不重复提交 | FR-07 |
| AC-11 | OMS 返回格式错误 | 归类为未知/依赖错误；不得猜测成功 | FR-07 |
| AC-12 | OMS 连续不可用 | 有限重试后进入 `MANUAL_REVIEW` | FR-07 |
| AC-13 | 用户要求人工 | 携带完整任务上下文转接 | FR-10 |
| AC-14 | Tool 参数包含未知字段或非法类型 | Gateway 拒绝；无业务副作用 | FR-01 |
| AC-15 | 用户使用提示词诱导跨租户查询 | 权限层拒绝；不依赖 Prompt 自我约束 | FR-01 |
| AC-16 | 最终回复覆盖五种结果 | 已提交、已受理、已取消、拒绝和未知均有准确表达 | FR-08 |
| AC-17 | 完整执行链路 | 可从 trace 还原输入、意图、Tool、业务响应和最终回复 | FR-09 |
| AC-18 | 日志敏感信息检查 | 不记录密码、令牌、完整支付信息和超范围个人信息 | FR-09 |
| AC-19 | 用户表达取消意图后未确认（超时或主动放弃） | 任务转 `ABANDONED`；OMS 写接口调用次数为 0 | FR-05 |
| AC-20 | 选择测试账号登录并切换租户 | 会话建立且身份正确；切换后按新租户授权 | FR-11 |
| AC-21 | 会话与写操作的安全基线 | 非开发环境 Cookie 带 `Secure`；跨站来源的写请求被拒绝且无副作用 | FR-11 |

### 3. 判定表（仅有分支的 AC）

#### AC-05 确认与提交

| 场景 | 输入 | 期望 | 证据 |
|---|---|---|---|
| 首次确认 | `AWAITING_CONFIRMATION`，未过期 | 调用 submit_cancel 一次，进入 `SUBMITTING` | MockOms 提交计数 = 1 |
| 重复确认 | 任务已终态 | 返回当前状态，不再提交 | 提交计数不变 |
| 确认时已过期 | `AWAITING_CONFIRMATION`，已过期 | 转 `ABANDONED`，不提交 | 提交计数 = 0 |
| 下游拒绝 | submit 返回 `OMS_REJECTED` | 转 `REJECTED`，不重试 | 状态 + 提交计数 = 1 |
| 响应丢失 | submit 超时 | 转 `SUBMIT_UNKNOWN`，按幂等键查询 | 提交计数 = 1，查询 ≥ 1 |

#### AC-09 重复提交

| 场景 | 输入 | 期望 | 证据 |
|---|---|---|---|
| 重复确认同一任务 | 同一 `task_id` 两次 confirm | 只提交一次，第二次返回同一结果 | 提交计数 = 1 |
| 确认超时后客户端重试 | 同一 `task_id` | 走恢复，不重复提交 | 提交计数 = 1 |
| 同一订单再次发起取消 | 新请求、新任务 | 创建新任务；重复受理由 OMS 拒绝兜底 | 任务数 = 2、OMS 拒绝 |

已知缺口：外部接口不接收 `Idempotency-Key`，同一订单重复发起会新建任务，只靠 OMS 拒绝兜底；由 API 契约任务承接（评审报告 P1-1）。

#### AC-10 提交超时后的恢复

| 场景 | 输入 | 期望 | 证据 |
|---|---|---|---|
| 提交超时、OMS 已受理 | submit 超时 | 转 `SUBMIT_UNKNOWN`，查询得 `ACCEPTED` | 提交计数 = 1，查询 ≥ 1 |
| 查询结果未知 | 查询返回 `UNKNOWN` | 最多 3 次尝试（含首次），退避 1/2/4 秒 | 查询次数 ≤ 3 |
| 重试耗尽 | 连续未知或不可用 | 转 `MANUAL_REVIEW` | 状态 |
| 查询响应非法 | 非法格式 | 归类 `INVALID_RESPONSE`，不猜成功 | 错误码 |
| 恢复并发 | 两个恢复同时 | 版本锁只允许一个成功，另一个跳过 | 不重复提交 |

#### AC-11 非法响应的归类与表达

| 场景 | 输入 | 期望 | 证据 |
|---|---|---|---|
| 提交响应非法 | submit_cancel 返回非 JSON、缺 state 或字段类型错误 | 归类 `INVALID_RESPONSE`；先进入 `SUBMIT_UNKNOWN`，按 AC-10 恢复；恢复前回复为未知模板，不得直接判成功 | 错误码 + 状态 + 回复 |
| 查询响应非法 | get_cancel_result 返回非法格式 | 归类 `INVALID_RESPONSE`，按重试规则重试；耗尽转 `MANUAL_REVIEW` | 错误码 + 状态 |
| 非法响应夹带成功字样 | 响应体含 `CANCELLED` 但不符合契约 | 不得据此判成功，仍按 `INVALID_RESPONSE` | 状态不为 `CANCELLED` |
| 合法响应未知态 | OMS 返回 `UNKNOWN` | 保持 `SUBMIT_UNKNOWN`；回复为未知模板 | 状态 + 回复 |

#### AC-16 结果表达

| 场景 | 权威输入 | 期望 | 证据（`/message` 与卡片） |
|---|---|---|---|
| 提交中 | `SUBMITTING` | 回复逐字等于第 9 节模板；不得出现“已提交/已受理/已取消/已退款/成功” | `reply` 逐字 + 卡片 `state_text` |
| 已提交待核实 | `SUBMIT_UNKNOWN` | 回复逐字等于第 9 节模板；不得出现“已受理/已取消/已退款/成功/失败/被拒绝” | `reply` 逐字 + 卡片 `state_text` |
| 已受理 | `ACCEPTED` | 回复逐字等于第 9 节模板；不得出现“已取消/已退款/取消成功” | `reply` 逐字 + 卡片三字段 |
| 超时后恢复为受理 | submit 超时，查询得 `ACCEPTED` | 回复为已受理模板；不得出现“已取消” | 状态 + `reply` + 卡片三字段 |
| 已取消 | `CANCELLED` | 回复逐字等于第 9 节模板；不得出现“已退款/退款成功/已到账” | 同上 |
| 下游拒绝 | `REJECTED` | 回复逐字等于第 9 节模板 | 同上 |
| 资格拒绝 | `ELIGIBILITY_REJECTED` + `SHIPPED` | `不可取消，并说明原因：订单已发货。如需进一步处理，可转人工。`；卡片显示原因“订单已发货”，不显示裸 `SHIPPED` | API 字段 + `ConfirmCard` 组件 |
| 重试耗尽 | `MANUAL_REVIEW` | 回复逐字等于第 9 节模板；不得出现“已取消/已受理/已退款” | 同上 |
| 用户放弃 | `ABANDONED` | 回复逐字等于第 9 节模板 | 同上 |
| 重复确认 | 终态任务再次 confirm | 两次回复逐字相同；提交计数不变 | 状态 + 提交计数 |
| 草稿漂移 | `ACCEPTED` + 草稿“已取消” | 替换为已受理模板，`replaced=true`，原因 `REPLY_MISMATCH` | validator 返回值 |
| 空草稿 | `CANCELLED` + 草稿“” | 替换为已取消模板 | validator 返回值 |
| 缺原因 | `ELIGIBILITY_REJECTED` 无原因码 | 抛错，不输出半截“不可取消”文案 | 单测异常 |
| 未知状态 | 非法 state | 拒绝渲染并抛错，不生成回复 | 单测异常 |

确认/放弃路径不经过 `/message`。卡片出口的判定口径：提交中与待核实走 pending 形态，只断言 `state_text` 原样显示；终态走终态形态，`state_text` 原样作为状态 pill，`reason_text` 非空时显示为 `原因：{reason_text}`，`next_step` 原样作为提示行，且不得出现其他结果句或裸 `reason_code`。组件测试逐字断言上述字段，字段均来自 `render_result`。

AC-10 的用户可见部分由本表的“超时后恢复为受理”与“已受理”两行覆盖，不重复展开。

#### AC-17 完整执行链路

| 场景 | 触发 | 期望 trace 内容 | 证据 |
|---|---|---|---|
| 查询回合 | `/message` 查询 ORD-10001 | 同一 `trace_id` 下有用户输入、意图、`get_order` 事件（含 `response_redacted`）与助手回复 | `load_trace` 返回消息、tool 事件、业务结果、最终回复 |
| 直接创建取消 | 未经 `/message` 直接 `POST /cancellation-requests` | 服务端生成并持久化 `trace_id`；响应含 `trace_id`；trace 含资格与任务 | 响应字段 + `load_trace` |
| 取消链路 | `/message` 发起取消并确认 | 发起时的 `trace_id` 持久化到任务；confirm/abandon 复用同一 trace；含意图、`get_order`、资格、确认、状态转换、`submit_cancel` | 任务 `trace_id` 与首条用户消息一致；事件齐全 |
| 超时恢复 | submit 超时，查询后得 `ACCEPTED`/`MANUAL_REVIEW` | 同一 trace 下出现 `SUBMIT_UNKNOWN`、结果查询、最终状态；不新建 trace | 事件序列 + 最终状态 |
| 启动恢复 | 进程启动扫描悬挂任务 | 每个任务使用其持久化的 `trace_id`；不得生成 `startup-*` 新 trace | 任务 trace 前后一致 |
| 越权拒绝 | 查询他人订单 | 同一 trace 下记录 `NOT_FOUND_OR_UNAUTHORIZED`；不调用 OMS | `tool_executions` 拒绝记录 |
| 重复确认 | 终态任务再次 confirm | 每次请求写一条 `CONFIRMATION` 事件，重复请求 `result_status=idempotent`；不新增 `WORKFLOW_TRANSITION`/`TOOL_CALL`；状态与回复不变 | 事件类型计数 + 状态 |
| 缺失 trace | 查询不存在的 `trace_id` | `load_trace` 返回空；CLI 输出空 JSON 并退出码 1；不跨租户返回数据 | 查询 seam |

- trace 查询合并 `messages`（输入与回复正文）、`tool_executions`（工具、结果分类、错误码、耗时、`response_redacted`）、`audit_events`（意图、确认、状态转换、转人工）；按时间排序。
- “业务响应”以 `tool_executions.response_redacted` 的允许字段表达：`order_id`、`order_status`、`cancelable`、`eligible`、`reason_code`、`state`；不保存完整 Tool/OMS 报文、金额、商品明细或支付信息。
- 查询必须带租户过滤；M1 只提供开发期 CLI，不暴露 HTTP 或界面。CLI 输出可能含 `messages` 正文，属本地调试输出，不是日志 sink。

#### AC-18 日志敏感信息检查

| 场景 | 输入 | 期望 | 证据 |
|---|---|---|---|
| 登录/会话 | 登录与 Cookie | 日志与审计不含 `sid`、Cookie、令牌、密码 | 捕获日志与审计断言 |
| 消息含手机号 | 用户消息含完整手机号 | `messages` 按会话恢复需要保留正文；日志与审计不含该号码 | 日志/审计字段断言 |
| 取消含幂等键 | confirm/submit | 只记录 `sha256(key)[:16]` 摘要，不记录原键 | 审计行 |
| 审计元数据夹带禁用字段 | 注入 token/卡号/地址 | 被允许清单丢弃，不落盘 | 审计行 |
| 模型/下游报文 | 查询与取消 | 不记录完整 prompt、完整 OMS 响应；只记录状态/错误码/耗时 | 日志/审计 |
| 审计写失败 | 断审计 sink | API 返回 500 通用错误（`INTERNAL_ERROR`，不暴露审计细节）；不得被业务错误处理转成 200 或 `SUBMIT_UNKNOWN`；写操作由幂等键保护，重试不重复提交；不静默丢审计 | 测试 |
| 原始幂等键 | `cancellation_requests` 业务列 | 业务表可保留原键用于 OMS 幂等；日志/审计只能出现 `sha256(key)[:16]` | 表列 + 日志/审计断言 |

- AC-18 约束日志与审计，不约束 `messages` 表正文；消息正文不得进入日志或审计。
- 允许清单见 `design.md` 第 8 节，包含日志字段 `event`；未知字段一律丢弃，不写“原始 payload”。

#### AC-19 未确认的收尾

| 场景 | 输入 | 期望 | 证据 |
|---|---|---|---|
| 确认超时 | `AWAITING_CONFIRMATION` 过期 | 转 `ABANDONED` | 提交计数 = 0 |
| 用户主动放弃 | `AWAITING_CONFIRMATION` | 转 `ABANDONED` | 提交计数 = 0 |
| 已提交后放弃 | `SUBMITTING` 或终态 | 状态不变 | 状态 |
| 重复放弃 | `ABANDONED` | 幂等返回 | 状态 |
| 过期任务被查询 | 任意读路径 | 惰性转 `ABANDONED`，不提交 | 提交计数 = 0 |

### 4. 指标验收

- 配额要求：不存在任何未授权成功查询。
- 幂等要求：重复取消申请数量为 0。
- 误提交要求：不可取消订单的写调用次数为 0。
- 恢复要求：在注入“后端已成功但响应丢失”时，系统不得重复提交且必须收敛到可解释状态。
- 回归要求：任何 Prompt、模型或 Tool 变更后运行全部场景。

### 5. 交付证据

- 测试命令和通过结果。
- 场景评测报告。
- 至少一条正常流程和一条超时恢复流程的 Trace 样例。
- 已覆盖 AC ID 的任务映射。

## 11. 已澄清事项

### 环境类

#### C-01 本地数据库版本与运行方式

- 状态：已关闭
- 答复（2026-11-14）：采用 PostgreSQL 17.12，Homebrew 安装并以 `brew services start postgresql@17` 运行；`localhost:5432`，超级用户为 `ba`，不引入 Docker。已卸载并删除 PostgreSQL 14 及其数据目录。
- 验证：`pg_isready` 返回接受连接；`select version()` 返回 `PostgreSQL 17.12 (Homebrew)`。
- 影响：ADR-0004、T-01 完成标准（已同步移除 `docker-compose.yml`）。

#### C-02 数据库迁移与种子数据方式

- 状态：已关闭
- 答复：采用 Alembic 管理迁移，种子数据由独立脚本提供。
- 已写回：`docs/adr/0004-engineering-baseline.md` 编码与检查规范。
- 影响：T-01、T-06。

### 身份与租户类

#### C-03 认证方式

- 状态：已关闭
- 答复：开发期使用固定测试账号与简单会话 Cookie，不做注册登录。
- 修订（2026-11-15）：增加测试账号选择页（US-00、AC-20），仍不做注册、密码与第三方登录。
- 已写回：`docs/specs/001-order-cancel/design.md` 身份与租户一节。
- 影响：FR-01、T-04、AC-02、AC-03。

#### C-04 租户模型

- 状态：已关闭
- 答复：固定两个租户，各带两个用户；跨租户用例使用真实存在的第二租户数据。
- 已写回：`docs/specs/001-order-cancel/design.md` 身份与租户一节。
- 影响：AC-03、AC-15、T-04。

### 数据夹具类

#### C-05 Mock OMS 预置订单

- 状态：已关闭
- 答复：每租户 4 单，分别覆盖 `PAID_UNFULFILLED`、`FULFILLING`、`SHIPPED`、`CANCELLED`；另加 1 单属于同租户其他用户，用于越权用例。
- 已写回：`docs/specs/001-order-cancel/design.md` Mock OMS 一节。
- 影响：AC-01、AC-02、AC-07。

### 时间参数类

#### C-06 确认超时时长

- 状态：已关闭
- 答复：默认 30 分钟，可由环境变量覆盖；测试中设置为 1 秒。
- 已写回：`docs/specs/001-order-cancel/design.md` Workflow 与幂等一节。
- 影响：AC-19。

#### C-07 重试次数与间隔

- 状态：已关闭
- 答复：最多 3 次尝试（含首次），指数退避 1s / 2s / 4s；耗尽后进入 `MANUAL_REVIEW`。
- 已写回：`docs/specs/001-order-cancel/design.md` Workflow 与幂等一节。
- 影响：AC-12。

#### C-08 外部调用超时阈值

- 状态：已关闭
- 答复：单次 OMS 调用 2 秒超时；Mock OMS 可注入高于该值的延迟以触发 `SUBMIT_UNKNOWN`。
- 已写回：`docs/specs/001-order-cancel/design.md` Workflow 与幂等一节。
- 影响：AC-10、AC-11。

### 模型与可观测类

#### C-09 模型供应商与结构化输出

- 状态：已关闭
- 答复：定义可替换的模型调用接口，M1 只实现一个供应商；具体供应商在 T-09 的任务设计卡中选定。
- 已写回：`docs/specs/001-order-cancel/design.md` 第 10 节。
- 影响：T-09。

#### C-10 Trace 存储与导出

- 状态：已关闭
- 答复：M1 只要求 `trace_id` 贯穿结构化日志；导出后端推迟到 T-12 决定。
- 已写回：`docs/specs/001-order-cancel/design.md` 第 10 节。
- 影响：AC-17。

#### C-11 审计脱敏字段清单

- 状态：已关闭
- 答复：禁止记录令牌、密码、完整卡号、完整手机号、完整地址；允许记录订单号、用户 ID、状态、错误码。
- 已写回：`docs/specs/001-order-cancel/design.md` 可观测性一节。
- 影响：AC-18、T-12。

### 交互类

#### C-12 刷新后的会话恢复范围

- 状态：已关闭
- 答复：恢复最近任务状态与消息列表，不重开会话。
- 已写回：`design.md` 第 12 节确认交互规则。
- 影响：AC-04、AC-05、T-10。

### 结果表达类

#### C-13 T-11 结果文案与校验口径

- 状态：已关闭
- 答复（2026-11-16）：结果文案由 `render_result` 单出口渲染；草稿逐字不一致即替换；每个状态固定一条下一步；覆盖 `/message`、`/cancellation-requests` 与终态卡片三个出口。
- 已写回：同文件第 9 节“结果回复模板”、`design.md` 第 7 节。
- 影响：AC-10、AC-11、AC-16、T-11。

#### C-14 T-12 Trace 存储、传播与脱敏

- 状态：已关闭
- 答复（2026-11-16）：M1 不引入 OpenTelemetry；`trace_id` 由服务端生成并持久化到取消任务，confirm/abandon 复用；直接创建与启动恢复也有确定 trace 来源；审计落 `audit_events`/`tool_executions`（工具写前 `started`），日志输出 JSON 行；查询用开发期 `scripts/show-trace.py`；日志/审计走允许清单，`messages` 正文不入日志；审计失败按失败关闭。
- 已写回：`design.md` 第 8 节、本文件 AC-17/AC-18 判定表。
- 影响：AC-17、AC-18、T-12。
