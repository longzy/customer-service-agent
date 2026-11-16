# 当前项目状态

- 更新日期：2026-11-16
- 项目阶段：M1 订单查询与未发货订单取消（M0 出口条件已满足）
- 当前状态：进行中
- 当前 Milestone：M1（规格已批准：`docs/specs/001-order-cancel/`）
- 当前工作：T-11 结果校验（未开工）；T-12 Trace 与审计、T-13 场景评测待承接
- 应用代码：查询、取消、转人工与登录闭环已实现；剩余结果校验、可观测与评测
- 版本控制：`main` 分支，114 次提交，工作区干净

<!-- verify:start -->
- 最近验证：`./scripts/verify.sh` 全部检查通过——pytest 318 passed（独立测试库）、mypy 36 个文件、追溯矩阵通过（21 条 AC）、文档与前端检查通过
<!-- verify:end -->

## M1 出口条件

M1 完成的定义见 `docs/roadmap.md`：全部 20 条验收用例通过、越权与重复操作为 0、正常/拒绝/异常/恢复场景均有自动化证据。当前 18 条 AC 有测试引用，AC-17 与 AC-18 由 T-12 承接（见 `scripts/trace-baseline.txt`）。

## 当前允许的工作

- 推进 T-11 结果校验、T-12 Trace 与审计、T-13 场景评测。
- 按 `docs/process/WORKFLOW.md` 修复门禁、补齐工程标准（草案，待批准）。
- 修订现有规格与验收用例；补齐接口契约与迁移。

## 当前不允许的工作

- 直接接入真实订单、支付或物流系统。
- 扩展全渠道、售前导购、营销或完整人工坐席后台。
- 引入多 Agent 自主协作框架。
- 在规格和验收尚未批准时大规模生成业务代码。

## 已完成

- M0 基线：原始评审归档、产品宪章、架构基线、不变量、路线图与 AI Coding 规范。
- ADR-0001 至 ADR-0004 全部批准；M1 规格批准，验收用例 20 条。
- 工程骨架与门禁：uv + FastAPI + Alembic、Next.js + TS strict、pre-commit/pre-push、`scripts/verify.sh`。
- T-01 至 T-10、T-14 至 T-19 全部完成并通过独立评审（16 张执行卡、16 份评审记录）。
- T-02 领域契约：10 个取消状态映射、7 个错误码、契约反例测试。
- T-06 Mock OMS：夹具、幂等提交、故障规则与开发期管理接口。
- T-07/T-08 取消资格 Policy Engine 与 Cancellation Workflow：状态机、确认/放弃、恢复重试、乐观锁。
- T-09/T-17/T-18 查询链路：意图识别、订单 Tool、Conversation API 与真实 DeepSeek 接入。
- T-10/T-14/T-16 前端：登录页、查询视图、确认卡片与会话门禁。
- T-15/T-19 人工转接上下文与启动恢复。
- T-20 会话安全基线：`Secure` Cookie、跨站写请求拒绝、密钥扫描（AC-21，两轮评审通过）。
- 工作流 v2 与工程标准已批准；服务端 CI、状态派生视图按此执行。
- 2026-11-16 开发规范评审与工作流 v2 草案：`docs/reviews/2026-11-16-dev-standards-review.md`、`docs/process/WORKFLOW.md`、`docs/process/standards.md`。

## 进行中

- M1 剩余任务 T-11、T-12、T-13 均未开工，尚未建执行卡。
- T-11 结果校验：`services/agent_runtime/validator.py`，承接 AC-16 的回复校验。
- T-12 Trace 与审计：承接 AC-17、AC-18，含请求级 trace_id 贯穿与日志脱敏。
- T-13 场景评测：`evals/` 仍是空占位。

## 阻塞

- 无。

## 下一步

1. 为 T-11 出执行卡并实现结果校验，先红后绿。
2. 完成 T-12：请求级 trace_id、审计落盘、日志脱敏，并删除 `scripts/trace-baseline.txt` 中对应两行。
3. 完成 T-13：把 AC-01 至 AC-20 组织为可重复运行、有通过率阈值的情景评测。
4. 按评审报告第 3 节处理 P0 项：服务端 CI、状态事实源、测试库隔离、安全基线。

## 待确认决策

业务与范围：

- 首个交互入口使用简单 Web Chat，不接第三方渠道。
- 模拟 OMS 作为唯一业务系统，真实集成放到后续阶段。

工作流 v2（2026-11-16 提出，待批准）：

- 是否采用 `docs/process/WORKFLOW.md` 的变更分级（T0–T3）与门禁阶梯（G0–G4）。
- 是否以服务端 CI 取代本地 hook 作为唯一硬门禁，并把本地 hook 降级为快速反馈。
- 是否把 `CURRENT.md` 改为由 `scripts/check-status.py` 校验的派生视图，禁止手工维护多份状态。
