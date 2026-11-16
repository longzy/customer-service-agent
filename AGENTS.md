# AGENTS.md

## 沟通

- 与用户沟通、代码注释、文档和提交说明默认使用中文。
- 代码标识符、协议字段和第三方 API 保持其行业通用英文命名。

## 每次开工必须执行

1. 阅读 `docs/CURRENT.md` 与 `docs/process/WORKFLOW.md`。
2. 在回复中复述当前阶段、已完成项、进行中项、阻塞项和下一步。
3. 根据任务继续读取：
   - 产品范围：`docs/product/charter.md`。
   - 架构变化：`docs/architecture/overview.md` 和 `docs/architecture/invariants.md`。
   - 业务实现：当前 Milestone 的 Spec 和 Acceptance。
   - 架构取舍：相关 `docs/adr/`。
   - 接管未完成任务：`docs/handoffs/` 中最新的相关记录。

恢复结果与用户当前指令不一致时，以用户当前指令为准，并先更新 `docs/CURRENT.md` 再继续。

## 文档权威顺序

如果文档之间存在冲突，按以下权威顺序处理：

1. 产品宪章和安全/架构不变量。
2. 已批准 ADR。
3. 当前 Milestone 规格与验收用例。
4. 任务清单和代码。

发现冲突时先停止实现并报告，不得自行选择更方便的解释。

## 当前仓库状态

- 阶段、当前 Milestone、进行中、阻塞与下一步以 `docs/CURRENT.md` 为准，本文件不重复维护。
- 一键验证：`./scripts/verify.sh`（步骤以脚本为准，不要在此处复制清单）。
- 后端依赖 `UV_CACHE_DIR=./.uv-cache uv sync`；前端依赖 `pnpm -C apps/web install`。
- 集成测试：`./scripts/test-db.sh -q`（独立测试库，自动迁移；禁止直连开发库）。
- 状态与追溯：`python3 scripts/check-status.py`、`python3 scripts/trace.py --strict`。
- 门禁：服务端 CI 是唯一硬门禁（`verify`、`frontend-build` 两个 required check）；本地 `pre-commit`/`pre-push` 只做快速反馈。
- 命令以实际跑通为准；新增或变更构建、测试、Lint 命令时必须同步更新本文件与 `README.md`。

## 工程约束

执行任何业务变更前读取 `docs/architecture/invariants.md` 与 `docs/process/standards.md`。不变量、安全边界和完成标准只在其中定义，本文件不维护第二份副本。

## 执行工作流

按 `docs/process/WORKFLOW.md` 的变更分级与门禁阶梯执行；规则以 `docs/process/standards.md` 的 STD 编号为准。`sdd.md`、`tdd.md`、`review.md` 处于迁移期，只保留路径与测试细节。

## 提交与合并

- 提交信息遵循 Conventional Commits：`type(scope): 中文描述`，scope 用任务号或模块名。
- 一个提交只做一件事；依赖升级单独提交。
- 禁止 `--no-verify` 直推；绕过必须在 PR 写明原因，并在 24 小时内补跑完整门禁。
- 实现者不得为自己的改动签字；评审必须由未参与实现的上下文完成。

## 需要停止并请求决策的情况

- 要实现的能力不在当前 Milestone 范围内。
- 需要改变领域状态机、权限模型、租户模型或核心架构。
- 需要引入新的生产基础设施、外部付费服务或真实业务系统。
- 需求与产品宪章、ADR 或验收标准冲突。
- 需要处理真实用户数据、生产密钥或执行不可逆业务操作。
- 当前证据不足以判断业务规则，且错误实现会造成资金、隐私或合规风险。

