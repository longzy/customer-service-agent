# AGENTS.md

## 沟通

- 沟通、注释、文档与提交说明用中文；代码标识符、协议字段保持英文。

## 每次开工

1. 读 `docs/CURRENT.md`（一页事实，唯一状态视图）。
2. 按任务加载，不预读全仓：
   - 改代码：`docs/process/WORKFLOW.md`。
   - 改前端：`docs/process/frontend.md`。
   - 硬约束：`docs/architecture/invariants.md`、`docs/process/standards.md`。
   - 当前变更：`docs/specs/<spec>/`。
   - 架构取舍：相关 `docs/adr/`。
   - 事务与 seam 归属：`docs/architecture/overview.md`。
   - 接管：`docs/handoffs/` 最新一篇（归档，不默认加载）。

恢复结果与用户指令冲突时，以用户指令为准，先更新 `docs/CURRENT.md` 再继续。

## 文档权威顺序

1. 产品宪章与安全/架构不变量。
2. 已批准 ADR。
3. 当前规格与验收用例。
4. 任务清单与代码。

冲突时先停止并报告，不自行选择方便的解释。

## 命令

以 `README.md` 为准。验证用 `make verify-check`（默认一行摘要、保留退出码）；收口用 `make verify`。常用：`test-db.sh`、`check-status.py`、`trace.py`、`check-secrets.py`。

## 工作流

按 `docs/process/WORKFLOW.md` 的 T0–T3 分级与 G0–G4 门禁执行。服务端 CI 是唯一硬门禁，本地 hook 只做反馈。实现者不得为自己的改动签字。

## 提交

- Conventional Commits：`type(scope): 中文描述`，scope 用任务号或模块名。
- 一个提交只做一件事；依赖升级单独提交。
- 禁止 `--no-verify` 直推；绕过须在 PR 写明并在 24 小时内补跑。

## 停止并请求决策

- 能力不在当前 Milestone 内。
- 要改状态机、权限、租户或核心架构。
- 要引入生产基础设施、付费服务或真实业务系统。
- 与宪章、ADR 或验收冲突。
- 要处理真实数据、生产密钥或不可逆操作。
- 证据不足且错误代价涉及资金、隐私或合规。
