# 当前项目状态

- 更新日期：2026-11-17
- 项目阶段：M1 客户转人工闭环
- 当前状态：brief 已批准；plan 已写，等待一次评审
- 当前 Milestone：M1 企业核心客服闭环（客户转人工闭环）
- 方向重置：[2026-11-16 企业化方向重置](initiatives/2026-11-16-enterprise-reset.md)
- 当前工作：评审客户转人工闭环的 plan；通过后拆 features/执行卡

<!-- verify:start -->
- 最近验证：`./scripts/verify.sh` 全部检查通过——pytest 472 passed（独立测试库）、mypy 45 个文件、追溯矩阵通过（39 条 AC）、文档与前端检查通过
<!-- verify:end -->

## 进行中

- `003-customer-handoff` 客户转人工闭环：brief 已批准；plan 等待评审。
- 后续切片：订单查询（004）、取消（005）、安全硬化（006），未启动。
- 分支保护：GitHub 私有仓库套餐限制，待决定是否升级/公开；不阻塞核心业务。

## 下一步

1. 评审 `003-customer-handoff/plan.md`，通过后按 features 拆执行卡。
2. 一次只做一个垂直 feature；测试/演示通过才更新 `passes`。
3. 完成后再启动订单查询/取消/安全硬化。

## 已完成

- M0：宪章、架构、不变量、ADR-0001~0004、AI Coding 入口。
- M1-P（原型）：T-01–T-21 完成（21/21），含查询、取消、转人工、登录、结果文案与校验、Trace/审计、场景评测、G3 校准、会话安全基线；不作为企业 M1 出口。
- R0-1（产品重基线）：企业宪章、路线图、ADR-0005、总体架构与不变量已批准。
- R0-2（后端边界，T-22–T-28）：依赖检查器、platform/identity/domain 迁移、OmsPort/Mock/Http、factory 与配置注入、行为快照、收口与回滚演练；迁移基线 0，回滚树 413 passed。
- ADR-0006：M1 客户从匿名改为预置账号 + 密码登录；订单按客户账号归属，删除订单号+手机尾号校验。
- 客户转人工闭环 brief：10 条验收与 3 个垂直 feature 已批准；plan 已写。
- 流程：S0–S8 替换为 Frame → Plan → Build & Verify → Review & Ship；新 spec 使用 `brief/plan/features`。

## 阻塞

- 分支保护受 GitHub 私有仓库套餐限制；不影响核心开发。

## 待确认决策

- 客户演示账号数量与命名；Plan 评审时确定。
- 队列等待/SLA 是否展示给客户；Plan 评审时确定。
- 模型成本/延迟目标；Plan 评审时确定。
- 清理任务频率与审计归档方式；安全硬化切片确定。
- 分支保护：升级 GitHub Team、转 Public，或接受未强制。

## 当前不做

- 客户自助注册/OTP/MFA；主管/管理员角色与界面；M2 退款；微服务/Kafka/K8s；真实 OMS/支付/物流；知识库/全渠道/运营后台；队列自动分配。
