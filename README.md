# 企业 AI 客服系统

一个面向企业内部使用的 AI 客服系统：AI 默认自动回复客户并完成订单类任务，客户可随时转人工，人工坐席在工作台接管并闭环。

## 当前状态

项目阶段与当前进度以 [当前阶段](docs/CURRENT.md) 为准。

2026-11-16 已做企业化方向重置：此前的消费者 M1 归档为 M1-P 原型，仅保留为工程资产，不作为企业 MVP 出口。

企业 M1 目标是打通：

> 客户匿名聊天 -> AI 自动回复/查单取消 -> 转人工进入队列 -> 坐席登录领取并接管 -> 回复 -> 关闭或转回 AI

新 M1 已从 F-01（客户登录/会话恢复/登出）开始实现：`apps/chat` 是新客户入口，`apps/web` 与旧 `backend/` 路由保留为 M1-P 资产。退款、主管/管理员、客户自助注册、全渠道、OIDC/SSO 和真实 OMS 不在 M1 范围内。

## 文档入口

- [当前阶段](docs/CURRENT.md)
- [企业化方向重置](docs/initiatives/2026-11-16-enterprise-reset.md)
- [产品宪章](docs/product/charter.md)
- [路线图](docs/roadmap.md)
- [总体架构](docs/architecture/overview.md)
- [架构不变量](docs/architecture/invariants.md)
- [ADR-0005 企业客服边界](docs/adr/0005-enterprise-boundary.md)
- [术语表](docs/GLOSSARY.md)
- [标准开发工作流](docs/process/WORKFLOW.md)
- [工程标准 STD](docs/process/standards.md)
- [开发规范评审（2026-11-16）](docs/reviews/2026-11-16-dev-standards-review.md)
- [参与开发](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [初始技术评审](docs/reviews/2026-11-14-initial-architecture-review.md)
- [AI Coding 调研](docs/research/ai-coding-new-project-practices-2026-11-14.md)
- [UI 规范与组件规范](docs/design-system/ui-spec.md)
- [UI 组件参考](docs/design-system/ui-components.html)
- [工程基线](docs/adr/0004-engineering-baseline.md)
- [任务设计卡模板](docs/templates/task-design-card.md)

## 项目原则

- 先形成全局基线，再派生当前迭代规格。
- 真实业务闭环优先于演示；只有 OMS 等外部业务系统允许 Mock。
- 一个主 Agent + 领域 Tool + 确定性 Workflow + 真实坐席闭环。
- 模型负责理解和沟通，业务规则和权限由确定性代码执行。
- 回答正确不等于任务完成；以岗位端到端走查和评测证据判定成功。
- 原始评审、架构决策、当前规格和验收用例全部版本化保存。

## 切换 AI Coding 工具

工具支持 `AGENTS.md` 时会自动读取入口。Claude Code 和 Gemini CLI 分别使用根目录的 `CLAUDE.md` 与 `GEMINI.md` 作为轻量适配入口。

如果工具不会自动读取项目文件，在首次消息中发送：

```text
请先读取 AGENTS.md、docs/process/WORKFLOW.md 和 docs/CURRENT.md。
在修改任何文件前，用五项摘要确认：当前阶段、已完成、进行中、阻塞、下一步。
```

## 本地运行

环境：Python 3.12（`.python-version`）、Node 22、pnpm 10、PostgreSQL 17（本机服务）。

```bash
make dev
```

这一条命令会：

- 没有 `.env` 时从 `.env.example` 创建；
- 创建数据库 `customer_service`（不存在时）并执行迁移；
- 安装依赖；依赖未变化时自动跳过；
- 同时启动 API `http://127.0.0.1:8000` 与客户 Chat `http://localhost:3000`；Ctrl-C 一起停止。

需要自然语言演示时，先在 `.env` 填 `MODEL_API_KEY`；留空会用假模型，只适合测试。数据库连接可在 `.env` 用 `DATABASE_URL` 覆盖。

M1 演示账号：`customer_a`/`customer_b`；密码由 `.env` 的 `DEMO_PASSWORD` 决定，运行 `uv run python scripts/seed_demo.py` 创建或重置，密码不提交。

排障：`make status` 查看端口/数据库/迁移/模型/契约；`make dev-stop` 停止本地 3000/8000。
演示模型失败：把 `.env` 的 `MODEL_API_KEY` 置空，设 `FAKE_MODEL_MODE=timeout`（或 `error`），再 `make dev`。

## 验证与测试

```bash
# 一键验证：ruff、mypy、pytest（独立测试库）、路由覆盖、追溯、状态、文档、前端
make verify
./scripts/verify.sh --no-record   # CI 使用：只验证，不写回状态快照
make verify-fast                  # 后端快速反馈
make eval                         # 场景评测：pytest JUnit + AC 报告

# 单独运行
UV_CACHE_DIR=./.uv-cache uv run ruff check .
UV_CACHE_DIR=./.uv-cache uv run mypy backend
./scripts/test-db.sh -q            # 建测试库、跑迁移、再跑 pytest
python3 scripts/check-docs.py
python3 scripts/check-status.py    # CURRENT.md ↔ tasks.md ↔ 执行卡
python3 scripts/trace.py --strict  # AC ↔ 测试 ↔ 执行卡
./scripts/check-api-types.sh       # OpenAPI ↔ 前端生成类型
pnpm -C apps/web lint
pnpm -C apps/web typecheck
pnpm -C apps/web test
pnpm -C apps/chat lint
pnpm -C apps/chat typecheck
pnpm -C apps/chat test
```

数据库默认 `postgresql+asyncpg://ba@127.0.0.1:5432/customer_service`；`dev.sh` 会创建库并迁移，连接串可在 `.env` 用 `DATABASE_URL` 覆盖。

迁移：`uv run alembic revision --autogenerate -m "..."`；表结构随后续任务落地。

门禁分两层，**服务端 CI 是唯一硬门禁**，本地 hook 只负责早发现：

- 本地 hook（需在新 clone 执行一次 `git config core.hooksPath .githooks`）：
  - `commit-msg`：校验 Conventional Commits。
  - `pre-commit`：格式、静态检查、文档、状态与追溯检查。
  - `pre-push`：执行完整 `verify.sh`。
- 服务端（`.github/workflows/ci.yml`）：PR 必过 `verify` 与 `frontend-build` 两个 required check。

集成测试使用独立测试库（默认 `customer_service_test`），不会再读开发库。紧急情况可 `--no-verify`，但必须在 PR 描述中写明原因，并在 24 小时内补跑完整门禁。

