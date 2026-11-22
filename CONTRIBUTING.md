# 参与开发

本仓库的人与 AI Agent 走同一套流程。开工前先读 [AGENTS.md](AGENTS.md)、[当前状态](docs/STATUS.md) 与 [标准开发工作流](docs/process/WORKFLOW.md)。

## 环境

- Python 3.12（`uv`）、Node 22（`pnpm` 10）、PostgreSQL 17。
- 依赖安装：

```bash
UV_CACHE_DIR=./.uv-cache uv sync
pnpm -C apps/chat install
pnpm -C apps/workspace install
pnpm -C packages/contracts install
createdb customer_service       # 开发库
```

## 门禁

```bash
./scripts/verify.sh              # 全量验证并回写状态快照
./scripts/verify.sh --no-record  # 只验证（CI 使用）
./scripts/test-db.sh -q          # 独立测试库：建库 → 迁移 → 测试
python3 scripts/check-status.py  # STATUS.md ↔ tasks.md ↔ 执行卡
python3 scripts/trace.py --strict # AC 追溯矩阵
./scripts/mutation.sh backend.tools.policy  # 突变检查（不进 pre-commit）
```

提交前 hook 需要在本机安装一次：

```bash
git config core.hooksPath .githooks
```

## 提交

- 本地流程：`git switch -c <type>/<slug>` → 小步提交 → `git push -u origin <branch>` → `gh pr create`（先 `gh auth login`；`gh` 不可用时用网页创建 PR）。
- 格式：`type(scope): 中文描述`，类型限 `feat` / `fix` / `docs` / `refactor` / `test` / `chore`。
- scope 用任务号（`F-08`）或模块名（`api`、`web`）。
- 一个提交只做一件事；依赖升级单独提交。

## 合并

- 必须经过 PR，并通过服务端 required checks；禁止直推 `main`（`main-guard` 会把直推标红）。
- 必须由未参与实现的上下文评审；评审结论与逐 AC 结论写入 `docs/reviews/<spec>/T-XX.md`。
- 禁止 `--no-verify` 直推；紧急绕过需在 PR 中写明原因，并在 24 小时内补跑完整门禁。

## 文档

- 规格：`docs/specs/<NNN>-<slug>/`；执行卡：`docs/tasks/<spec>/F-XX.md`。
- 同一事实只写一处；`STATUS.md` 是派生视图，不记录历史过程。
- 新增或修改规则时同步更新 [工程标准](docs/process/standards.md) 的 STD 编号。

## 安全

发现漏洞请按 [安全策略](SECURITY.md) 私下报告，不要开公开 Issue。
