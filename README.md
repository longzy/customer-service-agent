# 电商智能客服 Agent

一个以电商客服为业务场景，验证 Agent 业务执行、可靠性、可观测性和质量评估能力的企业级参考项目。

## 当前状态

项目阶段与当前进度以 [当前阶段](docs/CURRENT.md) 为准。

首版目标是打通：

> 查询本人订单 -> 判断未发货订单能否取消 -> 用户确认 -> 幂等提交 -> 查询结果 -> 异常恢复

退款、全渠道、多 Agent 自由协作和完整运营后台不在 M1 范围内。

## 文档入口

- [当前阶段](docs/CURRENT.md)
- [术语表](docs/GLOSSARY.md)
- [产品宪章](docs/product/charter.md)
- [总体架构](docs/architecture/overview.md)
- [架构不变量](docs/architecture/invariants.md)
- [路线图](docs/roadmap.md)
- [标准开发工作流](docs/process/WORKFLOW.md)
- [工程标准 STD](docs/process/standards.md)
- [开发规范评审（2026-11-16）](docs/reviews/2026-11-16-dev-standards-review.md)
- [参与开发](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [初始技术评审](docs/reviews/2026-11-14-initial-architecture-review.md)
- [AI Coding 调研](docs/research/ai-coding-new-project-practices-2026-11-14.md)
- [M1 订单取消规格](docs/specs/001-order-cancel/requirements.md)
- [M1 界面设计](docs/specs/001-order-cancel/design.md)
- [UI 规范与组件规范](docs/design-system/ui-spec.md)
- [UI 组件参考](docs/design-system/ui-components.html)
- [M1 工程基线](docs/adr/0004-engineering-baseline.md)
- [M1 需求（含验收与澄清）](docs/specs/001-order-cancel/requirements.md)
- [T-01 任务设计卡](docs/tasks/001-order-cancel/T-01.md)
- [任务设计卡模板](docs/templates/task-design-card.md)

## 项目原则

- 先形成全局基线，再派生当前迭代规格。
- 一个主 Agent + 领域 Tool + 确定性 Workflow。
- 模型负责理解和沟通，业务规则和权限由确定性代码执行。
- 回答正确不等于任务完成；以业务结果和评测证据判定成功。
- 原始评审、架构决策、当前规格和验收用例全部版本化保存。

## 切换 AI Coding 工具

工具支持 `AGENTS.md` 时会自动读取入口。Claude Code 和 Gemini CLI 分别使用根目录的 `CLAUDE.md` 与 `GEMINI.md` 作为轻量适配入口。

如果工具不会自动读取项目文件，在首次消息中发送：

```text
请先读取 AGENTS.md、docs/process/README.md 和 docs/CURRENT.md。
在修改任何文件前，用五项摘要确认：当前阶段、已完成、进行中、阻塞、下一步。
```

## 本地运行

环境：Python 3.12（`.python-version`）、Node 22、pnpm 10、PostgreSQL 17（本机服务，库名 `customer_service`）。

```bash
# 依赖
UV_CACHE_DIR=./.uv-cache uv sync
pnpm -C apps/web install

# 一键验证：ruff、mypy、pytest（独立测试库）、路由覆盖、追溯、状态、文档、前端
./scripts/verify.sh
./scripts/verify.sh --no-record   # CI 使用：只验证，不写回状态快照
./scripts/verify.sh --fast        # 后端快速反馈：ruff/format/mypy/unit
./scripts/eval.sh                 # 场景评测：pytest JUnit + AC 报告

# 单独运行
UV_CACHE_DIR=./.uv-cache uv run ruff check .
UV_CACHE_DIR=./.uv-cache uv run mypy services
./scripts/test-db.sh -q            # 建测试库、跑迁移、再跑 pytest
python3 scripts/check-docs.py
python3 scripts/check-status.py    # CURRENT.md ↔ tasks.md ↔ 执行卡
python3 scripts/trace.py --strict  # AC ↔ 测试 ↔ 执行卡
pnpm -C apps/web lint
pnpm -C apps/web typecheck
pnpm -C apps/web test

# 启动开发服务器（先准备环境变量）
cp .env.example .env   # 含 ENVIRONMENT=development；默认 production 会关闭测试账号
UV_CACHE_DIR=./.uv-cache uv run uvicorn services.api.main:app --reload
pnpm -C apps/web dev   # 打开 http://localhost:3000，会引导到登录页
```

数据库：`createdb customer_service`；连接串默认 `postgresql+asyncpg://ba@127.0.0.1:5432/customer_service`，可用 `.env` 覆盖（见 `.env.example`）。

迁移：`uv run alembic revision --autogenerate -m "..."`；表结构随后续任务落地。

门禁分两层，**服务端 CI 是唯一硬门禁**，本地 hook 只负责早发现：

- 本地 hook（需在新 clone 执行一次 `git config core.hooksPath .githooks`）：
  - `commit-msg`：校验 Conventional Commits。
  - `pre-commit`：格式、静态检查、文档、状态与追溯检查。
  - `pre-push`：执行完整 `verify.sh`。
- 服务端（`.github/workflows/ci.yml`）：PR 必过 `verify` 与 `frontend-build` 两个 required check。

集成测试使用独立测试库（默认 `customer_service_test`），不会再读开发库。紧急情况可 `--no-verify`，但必须在 PR 描述中写明原因，并在 24 小时内补跑完整门禁。

