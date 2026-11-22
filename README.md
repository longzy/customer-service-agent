# 企业 AI 客服系统

一个面向企业内部使用的 AI 客服系统：AI 默认自动回复客户并完成订单类任务，客户可随时转人工，人工坐席在工作台接管并闭环。

## 当前状态

项目阶段与当前进度以 [当前阶段](docs/STATUS.md) 为准。

2026-11-16 已做企业化方向重置：此前的消费者 M1 归档为 M1-P 原型，仅保留为工程资产，不作为企业 MVP 出口。

企业 M1 目标是打通：

> 客户登录 -> AI 自动回复/转人工 -> 进入队列 -> 坐席登录领取并接管 -> 回复 -> 关闭或转回 AI

截至 2026-11-21，M1 的 001/002/003 已收口：`apps/chat` 是客户入口，`apps/workspace` 是坐席工作台，`apps/web` 已退役；M1-P 的旧 Web 接口（`/session`、`/message`、`/handoff`、`/cancellation-requests`）已于 2026-11-19 退役，`agent_runtime`、`tools`、`workflows`（含订单取消工作流）保留供后续切片接入。退款、主管/管理员、客户自助注册、全渠道、OIDC/SSO 和真实 OMS 不在 M1 范围内。

## 文档入口

- [当前阶段](docs/STATUS.md)
- [企业化方向重置](docs/initiatives/2026-11-16-enterprise-reset.md)
- [产品宪章](docs/product/charter.md)
- [路线图](docs/ROADMAP.md)
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
- [项目驾驶舱](docs/dashboard.html)（`make dashboard` 生成）

## 文档模型

| 文件 | 回答什么 | 写入方式 |
|---|---|---|
| `docs/ROADMAP.md` | 阶段与出口条件 | 手写 |
| `docs/STATUS.md` | 现在在哪、下一步、卡在哪 | 手写 |
| `docs/specs/<spec>/requirements.md` | 为什么做、做什么、怎么算成功、AC | 手写，批准后冻结 |
| `docs/specs/<spec>/design.md` | 怎么做、为什么这么选、备选 | 手写，评审后冻结 |
| `docs/specs/<spec>/tasks.md` | 任务索引 | `make gen-tasks` 生成 |
| `docs/tasks/<spec>/F-XX.md` | 单任务范围、步骤、证据、回滚 | 手写；frontmatter 是状态源 |
| `docs/dashboard.html` | Roadmap / Board / Table | `make dashboard` 生成 |

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
请先读取 AGENTS.md、docs/process/WORKFLOW.md 和 docs/STATUS.md。
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
- 同时启动 API `http://127.0.0.1:8000`、客户 Chat `http://localhost:3000` 与坐席工作台 `http://localhost:3001`；Ctrl-C 一起停止。

需要自然语言演示时，先在 `.env` 填 `MODEL_API_KEY`；留空会用假模型，只适合测试。数据库连接可在 `.env` 用 `DATABASE_URL` 覆盖。

M1 演示账号：客户 `customer_a`/`customer_b`，坐席 `agent_1`/`agent_2`；密码由 `.env` 的 `DEMO_PASSWORD` 决定，运行 `uv run python scripts/seed_demo.py` 创建或重置，密码不提交。

排障：`make status` 查看端口/数据库/迁移/模型/契约；`make dev-stop` 停止本地 3000/3001/8000。非交互环境（CI/agent）会自动按非 TTY 安装依赖；依赖已就绪时可 `make dev ARGS=--no-install` 跳过安装。
演示模型失败：把 `.env` 的 `MODEL_API_KEY` 置空，设 `FAKE_MODEL_MODE=timeout`（或 `error`），再 `make dev`。

演示数据可随时回到干净起点：`make dev-reset`（停 3000/3001/8000、重建开发库、迁移并重播种；非交互运行用 `make dev-reset ARGS=--yes`）。开发库视为可抛弃资源，不要在里面存长期数据；不要手写 `DELETE`/`UPDATE` 修改演示库，需要重置时只用该命令；生产环境与远端数据库会被脚本拒绝。

## 验证与测试

```bash
# 一键验证：ruff、mypy、pytest（独立测试库）、路由覆盖、追溯、状态、文档、前端检查与构建
make verify-changed ARGS=F-08     # 实现内环：按路径触发，只跑改动涉及的检查（后端/chat/workspace/文档/契约）
make verify-check                 # 送审门禁：全量验证，不写回 STATUS（保留退出码，默认一行摘要）
make verify                       # 收口：代码未变时复用慢检查，写回 STATUS
./scripts/verify.sh --no-record   # CI 使用：只验证，不写回状态快照
./scripts/verify.sh --verbose     # 排障：逐步输出完整日志
make verify-fast                  # 后端快速反馈
make review-check                 # 评审前置快检：机械规则 + 文档/状态/追溯/契约
make review-pack ARGS="F-08"      # 生成两轴评审包（固定点、diff、AC 原文、执行卡决策、命令）
make lint                         # ruff check + format check
make typecheck                    # mypy backend
make test                         # pytest（独立测试库）
make gen-contracts                # 改错误码/路由响应/表结构后：刷新契约、前端类型与测试快照
make gen-tasks                    # 从执行卡 frontmatter 生成三份 tasks.md
make dashboard                    # 生成 docs/dashboard.html 与 status.json（Roadmap/Board/Table）
make eval                         # 场景评测：pytest JUnit + AC 报告

# 单独运行
UV_CACHE_DIR=./.uv-cache uv run ruff check .
UV_CACHE_DIR=./.uv-cache uv run mypy backend
./scripts/test-db.sh -q            # 建一次性测试库、跑迁移、再跑 pytest（退出即删）
make test-reuse ARGS=...           # 复用固定测试库跑 pytest（迭代用）
python3 scripts/check-docs.py
python3 scripts/check-status.py    # STATUS.md ↔ tasks.md ↔ 执行卡
python3 scripts/check-review-prereqs.py  # 组件命名/trace 基线/STATUS 评审声称
python3 scripts/review_pack.py F-08       # 评审包；自动识别固定点
python3 scripts/trace.py --strict  # AC ↔ 测试 ↔ 执行卡（含部分覆盖）
python3 scripts/close_feature.py F-06 --check  # 收口前置条件；--apply 改 frontmatter 并生成 tasks.md
./scripts/check-contracts.sh     # 契约链：domain/OpenAPI/前端类型
pnpm -C apps/chat lint
pnpm -C apps/chat typecheck
pnpm -C apps/chat test
pnpm -C apps/workspace lint
pnpm -C apps/workspace typecheck
pnpm -C apps/workspace test
```

`verify.sh` 默认只输出一行摘要；失败时打印失败步骤与日志尾部。需要完整日志时加 `--verbose`，或 `./scripts/verify.sh --no-record > /tmp/verify.log 2>&1; echo $?`。

测试库默认按进程一次性创建并在退出时删除，并行会话（多个 agent/终端同时验证）不会互删数据。需要固定库名或保留现场时用 `TEST_DB_NAME=customer_service_test_<suffix>`、`TEST_DB_KEEP=1`。

数据库默认 `postgresql+asyncpg://ba@127.0.0.1:5432/customer_service`；`dev.sh` 会创建库并迁移，连接串可在 `.env` 用 `DATABASE_URL` 覆盖。

迁移：`uv run alembic revision --autogenerate -m "..."`；表结构随后续任务落地。

门禁分两层，**服务端 CI 是唯一硬门禁**，本地 hook 只负责早发现：

- 本地 hook（需在新 clone 执行一次 `git config core.hooksPath .githooks`）：
  - `commit-msg`：校验 Conventional Commits。
  - `pre-commit`：格式、静态检查、文档、状态与追溯检查。
  - `pre-push`：执行完整 `verify.sh`。
- 服务端（`.github/workflows/ci.yml`）：PR 必过 `verify` 一个 required check（已包含前端 lint/typecheck/test/build）。

集成测试使用独立测试库（默认 `customer_service_test`），不会再读开发库。测试也不读本地 `.env`（`test-db.sh` 设 `SETTINGS_ENV_FILE=/dev/null`），本地与 CI 使用同一份配置来源；要覆盖配置请用环境变量。紧急情况可 `--no-verify`，但必须在 PR 描述中写明原因，并在 24 小时内补跑完整门禁。

