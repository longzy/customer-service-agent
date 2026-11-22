# AGENTS.md

## 沟通

- 沟通、注释、文档与提交说明用中文；代码标识符、协议字段保持英文。

## 每次开工

1. 读 `docs/STATUS.md`（一页事实，唯一状态视图）。
2. 任务状态看 `docs/tasks/<spec>/F-XX.md` 的 frontmatter；`tasks.md`、`dashboard.html`、`status.json` 是生成物，不手改。
3. 按任务加载，不预读全仓：
   - 改代码：`docs/process/WORKFLOW.md`；先按变更形状查 `docs/architecture/recipes.md` 的触点清单。
   - 改前端：`docs/process/frontend.md`。
   - 硬约束：`docs/architecture/invariants.md`、`docs/process/standards.md`。
   - 当前变更：`docs/specs/<spec>/`。
   - 架构取舍：相关 `docs/adr/`。
   - 事务与 seam 归属：`docs/architecture/overview.md`。
   - 接管：`docs/handoffs/` 最新一篇（归档，不默认加载）。

恢复结果与用户指令冲突时，以用户指令为准，先更新 `docs/STATUS.md` 再继续。

## 文档权威顺序

1. 产品宪章与安全/架构不变量。
2. 已批准 ADR。
3. 当前规格与验收用例。
4. 任务清单与代码。

冲突时先停止并报告，不自行选择方便的解释。

## 命令

以 `README.md` 为准。实现内环用 `make verify-changed ARGS=F-XX`；送审前 `make verify-check` 跑一次全量；收口 `make verify` 复用代码指纹（只重跑快检查）并写回状态。迭代测试用 `make test-reuse ARGS=...` 复用固定测试库。常用：`test-db.sh`、`check-status.py`、`trace.py`、`check-secrets.py`。

## 工作流

按 `docs/process/WORKFLOW.md` 的 T0–T3 分级与 G0–G4 门禁执行。服务端 CI 是唯一硬门禁，本地 hook 只做反馈。实现者不得为自己的改动签字。

## 提交

- Conventional Commits：`type(scope): 中文描述`，scope 用任务号（如 `feat(F-26)`）或模块名；spec 编号不作 scope。
- 一个提交只做一件事；依赖升级单独提交。
- 禁止 `--no-verify` 直推；绕过须在 PR 写明并在 24 小时内补跑。

## 文档编辑

- 小改用 `edit` 精确替换；整段重写才用脚本，避免批量替换误伤。

## 停止并请求决策

- 能力不在当前 Milestone 内。
- 要改状态机、权限、租户或核心架构。
- 要引入生产基础设施、付费服务或真实业务系统。
- 与宪章、ADR 或验收冲突。
- 要处理真实数据、生产密钥或不可逆操作。
- 证据不足且错误代价涉及资金、隐私或合规。
