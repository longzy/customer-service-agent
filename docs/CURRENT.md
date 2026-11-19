# 当前项目状态

- 更新日期：2026-11-19
- 项目阶段：M1 客户转人工闭环
- 当前状态：F-12 坐席关闭/转回 AI 已完成并收口；F-11、F-10、F-09、F-08 已完成并收口
- 当前 Milestone：M1 企业核心客服闭环（客户转人工闭环）
- 方向重置：[2026-11-16 企业化方向重置](initiatives/2026-11-16-enterprise-reset.md)
- 当前工作：F-14 已完成并收口；F-13、F-12、F-11、F-10、F-09、F-08 已收口；F-15、F-16、F-17、F-18、F-19、F-20、F-21、F-22 待评审

<!-- verify:start -->
- 最近验证：`./scripts/verify.sh` 全部检查通过——pytest 678 passed（独立测试库）、mypy 67 个文件、追溯矩阵通过（20 条 AC）、文档与前端检查通过
<!-- verify:end -->

## 进行中

- F-15、F-16、F-17、F-18、F-19、F-20、F-21、F-22、F-23 待评审；视觉回归已用 ego-browser 完成。
- 后续切片：订单查询（003）、取消（004）、安全硬化（005）未启动。
- 分支保护：GitHub 私有仓库套餐限制，待决定是否升级/公开；不阻塞核心业务。

## 下一步

1. 后续切片订单查询（003）、取消（004）、安全硬化（005）按 roadmap 排期。
2. UI 改版（002）三件套草案已开（AC-40~49、9 个 feature）；批准后从 S1 令牌接入开工，S2/S3 各做一次独立评审。

## 已完成

- 重构（2026-11-19，后端按业务域组织）：HTTP 入口归位到 `identity/http.py`、`conversations/customer_http.py`、`conversations/workspace_http.py`，DTO 随域；`api/` 只保留装配、中间件与共享 HTTP 工具；OpenAPI 15 条路径不变，pytest 678 passed；决策见 ADR-0008。
- 清理（2026-11-19，M1-P 旧 Web 接口退役）：删除 `/session`、`/message`、`/handoff`、`/cancellation-requests`、`/accounts` 与旧内存身份/会话中间件及 8 个强绑定旧测试文件；保留 `agent_runtime`、`tools`、`workflows`（含订单取消工作流与启动恢复）、旧表与 OMS 适配器；重新生成 OpenAPI、前端类型与测试快照（15 条路由）。
- 流程改进（2026-11-19，评测门禁批次 A）：`evals/run.py` 的 AC 集合改为从 `docs/specs/*/brief.md` 动态发现，`AC-01~29` 不再参与门禁，`scripts/trace-baseline.txt` 中登记的待开工 AC 记 `待开工`、不算缺失；多轮场景只列覆盖当前 AC 的用例；同步 `evals/README.md`、场景测试说明与 7 条报告单测。
- 流程改进（2026-11-19）：测试库默认一次性隔离（并行评审/门禁不再互删数据）、`make gen-contracts` 一键刷新契约与两个测试快照、评审结论按首句判定词解析、评审者不并行跑全量门禁；新增 4 条脚本自测。
- F-14：客户甲/乙端到端闭环与跨客户隔离——两客户各自登录/聊天/转人工/被接管/回复/转回/关闭，甲读乙会话/消息 404 且与不存在不可区分，交接单按客户独立；4 条 AC-33 集成用例（双坐席、4 类消息负向探针）+ 三组反向验证；同一浏览器双 host UI 走查截图 `evals/reports/001-customer-handoff/F-14/`；双轴评审通过（`docs/reviews/001-customer-handoff/F-14.md`，2 轮、0 阻断）；提交 fda805b、97325c2、6d13306。
- F-13：审计与限速收口——`service_audit_events` 只追加（触发器拒绝行级改删）、401/403/429 安全事件、登录/消息限速、审计失败 503 回滚、客户消息/AI 回复/Origin 403 审计；20 条 AC-39 集成用例 + 反向验证 4 组 + 迁移回滚演练；三轴独立评审通过（2 轮、0 阻断，`docs/reviews/001-customer-handoff/F-13.md`）；提交 46783aa、39924aa、555847b。
- F-12：坐席在已领取/人工中关闭会话，或人工中转回 AI；转回后同一会话 AI 恢复历史，再次转人工生成新交接单且同会话仅一张 open 单；17 条 AC-38 集成用例 + 6 条工作台前端用例 + 三遍双身份走查；双轴评审通过（整改后增量复核 0 阻断，`docs/reviews/001-customer-handoff/F-12.md`）；提交 7aeb960、9266b3a、1147a0e、f7611e2、d76b796。
- F-11：客户在任意未关闭状态关闭会话，交接单/队列同事务关闭；关闭后再发 409，同键重放幂等；11 条 AC-38 集成用例 + 4 条前端用例 + 双身份走查；双轴评审通过（`docs/reviews/001-customer-handoff/F-11.md`）；提交 31f415b、f86e364、14583aa、ca81e6a。
- M0：宪章、架构、不变量、ADR-0001~0004、AI Coding 入口。
- M1-P（原型）：21 个任务完成（已归档，执行卡已删除），含查询、取消、转人工、登录、结果文案与校验、Trace/审计、场景评测、G3 校准、会话安全基线；不作为企业 M1 出口。
- R0-1（产品重基线）：企业宪章、路线图、ADR-0005、总体架构与不变量已批准。
- R0-2（后端边界）：依赖检查器、platform/identity/domain 迁移、OmsPort/Mock/Http、factory 与配置注入、行为快照、收口与回滚演练；迁移基线 0，回滚树 413 passed。
- ADR-0006：M1 客户从匿名改为预置账号 + 密码登录；订单按客户账号归属，删除订单号+手机尾号校验。
- 客户转人工闭环 brief：10 条验收与 3 个垂直切片已批准；plan 已按 Google 模板重排并批准；features 已批准（14 条）。
- 流程：S0–S8 替换为 Frame → Plan → Build & Verify → Review & Ship；新 spec 使用 `brief/plan/features`。
- 目录：`services/` → `backend/`；import、pyproject、mypy、mutmut、检查器、脚本、测试与文档同步，全量 verify 通过。
- 模板：`brief`（PR/FAQ）、`plan`（Google Design Doc）、`features`（Anthropic feature list）按主流结构重写；新增模板契约测试；features 改为 plan 批准后生成。001 的 brief/plan 已按新模板重排并批准。
- F-01：客户 scrypt 登录、24h session 轮换/撤销、会话恢复、跨客户 404、登录限速、请求关联标识；`apps/chat` 登录/会话门禁；13 条 AC-30 测试与双轴评审通过。
- F-02：客户消息、AI 回复、模型超时/异常自动转人工、`after_id` 真实游标、消息幂等键与客户聊天界面；12 条 AC-31 测试与双轴评审通过。
- OpenAPI 前端类型：production 形态导出、客户响应/错误模型、`openapi-typescript` 生成 `apps/chat/lib/api-types.ts`，`check-api-types.sh` 接入 verify/pre-commit/CI；ADR-0007。
- F-03：关键词（转人工/人工客服/真人/找人工）不调用模型直接入队、完整交接单（摘要/最近 20 条/AI 轨迹/原因/待办/脱敏/`order_count=0`）、意图事件与脱敏边界；16 条 AC-32 集成测试 + 33 条纯函数用例与双轴评审通过。
- F-04：自然表达/低置信（<0.6，含 0.6 边界）/问订单/超范围/模型回复护栏转人工，复用完整交接单且不展示模型回复；34 条纯函数用例 + 9 条 AC-32 集成测试，双轴评审通过（Standards 3 轮 / Spec 2 轮）。
- F-05：坐席 scrypt 登录、8h 绝对 session/轮换、登出、5/15min 登录限速、非 agent 403、未领取/他人/跨租户 404；`apps/workspace` 登录与 `/queue` 会话门禁；14 条 AC-34 集成测试 + 6 条前端用例，双轴评审通过（Spec 3 个阻断项已修复）。
- F-06：工作台队列 FIFO（`created_at, id`）与摘要（客户账号/显示名、等待秒数、原因、订单数 0、脱敏末条 ≤100），同租户只读、未领取详情 404、无自动分配；10 条 AC-35 集成测试 + 9 条前端用例，双轴评审通过（2 轮，0 阻断）。
- F-07：条件领取（`UPDATE ... WHERE status='QUEUED'` 单条条件更新）并发仅一人成功、其余 409 `CLAIM_CONFLICT`；跨租户/不存在 404、已关闭 409 `CONVERSATION_CLOSED`；同事务会话归属与状态分歧回滚；工作台领取按钮、409 提示刷新、会话入口页；9 条 AC-35 集成测试（含真并发）+ 8 条前端用例，双轴独立评审通过（2 轮，0 阻断，3 条整改关闭）。
- F-08：领取后接管（`CLAIMED → HUMAN_ACTIVE`、交接单 `CLAIMED → ACTIVE`）、客户“正在接入人工/人工已接入”系统消息、领取者完整上下文（客户/消息/AI 轨迹/交接单/待办）、第二坐席查看/接管 404；9 条 AC-36 集成测试 + 4 条前端用例 + 浏览器走查，双轴独立评审通过（2 轮，0 阻断，2 条整改关闭）。
- F-09：第二坐席越权矩阵（领取 409、查看/接管 404、404 与不存在资源不可区分、失败零副作用、并发仅归属者成功）；8 条 AC-36 集成用例 + 双坐席浏览器走查，独立双轴评审通过（C-1/C-2 已关闭）；提交 670c975、a99880a、da163b8、353c78e、c0c052f。
- F-10：坐席回复持久化（`POST /workspace/conversations/{id}/messages`，幂等重放）、工作台 3s 增量轮询（`GET .../messages?after_id=`）、人工中客户消息不触发 AI 且工作台可见；9 条 AC-37 集成用例 + 3 条新增前端用例 + 双身份浏览器走查（客户 1352ms 看到回复），双轴独立评审通过（0 阻断，建议已整改，关闭/转回与审计限速由后续切片承接）；提交 f5d194d。
- 前端代码规范（2026-11-18）：`docs/process/frontend.md` 草案落地，覆盖目录/组件/类型/Next 边界/样式/a11y/安全/AI 生成/测试；决策为两个应用各自维护、允许组件重复、不建共享包；现有缺口与强制点接入顺序见文档第 10 节。
- UI 改版规格（2026-11-18）：`002-ui-redesign` 的 brief/plan/features 草案落地（AC-40~49、9 个 feature、S1–S4 映射），trace 基线已登记；待批准后开工。
- UI 设计冻结（2026-11-18）：编号顺延为 002（原拟 005）；补 CSS Modules 承载、动效参数、响应式断点、视觉基线；`ui-spec` v4 与 `baseline/` 已落地，应用代码未改。
- 流程改进（2026-11-18）：验证默认摘要与 `--verbose`、check-docs 锚点/待创建路径、trace 按 feature 判部分覆盖、dev 非 TTY 安装、close_feature.py 收口检查、读模型投影/评审固定点/多身份走查模板、`make lint/typecheck/test`。
- 流程改进（2026-11-18，评审内环）：新增 `make verify-changed`（按变更范围跑定向 AC 测试、改动 app 的 lint/typecheck/test 与文档/状态/追溯/契约）、`make review-check`（组件命名、trace 基线归属、CURRENT/评审记录一致的机械前置）、`make review-pack`（两轴评审包）；接入 verify、pre-commit、README 与 WORKFLOW。
- 前端升级与目录（2026-11-18）：`apps/chat`、`apps/workspace` 升级 Next.js 16.4.6 + React 19.3 + ESLint 9 flat config（`next lint` 已移除，改用 `eslint .`）；目录迁到 `features/auth`、`features/chat`、`features/queue`、`features/conversation`，`app/` 只装配；`ChatShell` 拆出 `useChatMessages`，19/17 条前端用例与两应用 build 通过。

## 阻塞

- 分支保护受 GitHub 私有仓库套餐限制；不影响核心开发。

## 待确认决策

- UI 改版（2026-11-18，002）：设计已冻结——五张页面稿、`tokens.css` v2、`ui-spec` v4（组件契约 3.1–3.14、样式承载/动效/响应式/基线）、`baseline/` 冻结哈希；实现切片 S1–S3 待开工，应用代码未改。
- 前端类型由 OpenAPI 生成已按 [ADR-0007](adr/0007-openapi-frontend-types.md) 落地；CSS 统一用 `docs/design-system/tokens.css` 与 ui-spec 间距/气泡规范仍未落地，登记为 M1 技术债；前端规范见 [frontend.md](process/frontend.md)，ESLint 核心规则已接入，token 迁移与 stylelint 强制点待接。
- PII 脱敏范围：M1 仅覆盖大陆手机号（`+86`/分隔/全角）、邮箱、18 位身份证（含 `X/x`）；银行卡、护照、座机、非大陆号码等格式透传，归 005 安全硬化。
- plan 澄清（F-06 评审确认）：客户 cookie 访问 `/workspace/queue` 返回 401 而非 plan 5.1 的“客户→403”（403 指合法员工凭据但非 agent）；队列末条/等待起算口径在执行卡 D-2/D-3；003 接入订单后需重审 `order_count=0`。
- 清理任务频率与审计归档方式；安全硬化切片确定。
- 分支保护：升级 GitHub Team、转 Public，或接受未强制。

## 当前不做

- 客户自助注册/OTP/MFA；主管/管理员角色与界面；M2 退款；微服务/Kafka/K8s；真实 OMS/支付/物流；知识库/全渠道/运营后台；队列自动分配。
