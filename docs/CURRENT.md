# 当前项目状态

- 更新日期：2026-11-17
- 项目阶段：M1 客户转人工闭环
- 当前状态：F-02 客户消息与 AI 回复实现完成，待独立评审
- 当前 Milestone：M1 企业核心客服闭环（客户转人工闭环）
- 方向重置：[2026-11-16 企业化方向重置](initiatives/2026-11-16-enterprise-reset.md)
- 当前工作：F-02 待独立评审；实现与证据见执行卡

<!-- verify:start -->
- 最近验证：`./scripts/verify.sh` 全部检查通过——pytest 501 passed（独立测试库）、mypy 54 个文件、追溯矩阵通过（10 条 AC）、文档与前端检查通过
<!-- verify:end -->

## 进行中

- `001-customer-handoff` 客户转人工闭环：F-02 已实现，11 条 AC-31 定向测试与全量 `verify.sh` 通过，待独立评审。
- 后续切片：订单查询（002）、取消（003）、安全硬化（004），未启动。
- 分支保护：GitHub 私有仓库套餐限制，待决定是否升级/公开；不阻塞核心业务。

## 下一步

1. 独立上下文评审 F-02，结论写入 `docs/reviews/001-customer-handoff/F-02.md`；通过后再勾 `已完成`。
2. 一次只做一个 feature；测试/演示通过才更新 `passes`。
3. F-13 收口时补登录/登出/401/403/429 审计，并按评审记录补 seed smoke。

## 已完成

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

## 阻塞

- 分支保护受 GitHub 私有仓库套餐限制；不影响核心开发。

## 待确认决策

- 前端类型由 OpenAPI 生成、CSS 统一用 `docs/design-system/tokens.css` 与 ui-spec 间距/气泡规范：生成管线与样式统一未落地，F-01/F-02 沿用 M1-P 现状，登记为 M1 技术债。
- 清理任务频率与审计归档方式；安全硬化切片确定。
- 分支保护：升级 GitHub Team、转 Public，或接受未强制。

## 当前不做

- 客户自助注册/OTP/MFA；主管/管理员角色与界面；M2 退款；微服务/Kafka/K8s；真实 OMS/支付/物流；知识库/全渠道/运营后台；队列自动分配。
