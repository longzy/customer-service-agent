# ADR-0004：M1 工程基线与技术栈

- 状态：已批准
- 批准：2026-11-14（本次会话由用户确认）
- 日期：2026-11-14
- 关联：`docs/architecture/overview.md`、`docs/specs/M1/001-order-cancel/design.md`

## 背景

M1 规格已批准，但工程骨架缺少可执行依据：`overview.md` 第 7 节的技术基线标注为“拟定，需通过 ADR 确认后执行”，第 8 节目录标注为“建议方向”，仓库没有编码规范、Lint 规则，也没有前端界面规格。缺少这些输入时，T-01 只能由实现者凭习惯决定技术栈与代码风格，既无法评审，也无法回归。

本 ADR 固化 M1 的工程基线。具体依赖版本由 lockfile 承载，不在文档中重复维护。

## 决策

### 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 后端 | Python 3.12 + FastAPI | 异步 IO，OpenAPI 自动生成 |
| 后端依赖 | `uv` | 单个 `pyproject.toml` + `uv.lock` |
| 数据库 | PostgreSQL 17 | 本机 Homebrew 服务，`localhost:5432`，不引入容器 |
| 前端 | Next.js（App Router）+ TypeScript strict | `apps/web`，包管理用 `pnpm` |
| 契约 | OpenAPI 为唯一来源 | 前端类型由 OpenAPI 生成；JSON Schema 只用于 Tool 输入 |
| 可观测 | 结构化日志 + `trace_id` 贯穿 | OpenTelemetry SDK 在 T-12 接入 |
| 测试 | pytest（后端）、Vitest + Testing Library（前端） | 单元与集成分层 |

版本策略：依赖锁定大版本，lockfile 入库；升级单独提交并附回归结果。

### 目录与包边界

沿用 `overview.md` 第 8 节命名。Python 侧为一个 `uv` 项目，避免 M1 阶段的构建复杂度：

```text
pyproject.toml                # 后端与 evals 共用
services/
  api/                        # Conversation API、身份与会话
  agent_runtime/              # 意图、上下文、模型调用、Tool 规划
  tools/                      # Tool Registry 与授权网关
  workflows/                  # 取消等显式流程
  mock_oms/                   # 模拟订单系统
apps/web/                     # Next.js Web Chat（pnpm）
packages/contracts/           # OpenAPI 与生成的类型
evals/                        # 场景集与报告
tests/unit/
tests/integration/
```

包边界约束与 `overview.md` 一致，此处固化为可检查项：

- `agent_runtime` 不得 import `mock_oms`。
- `workflows` 只能经 Tool/Adapter 访问业务系统。
- `apps/web` 不含订单业务规则。
- `packages/contracts` 是跨模块接口的唯一定义来源。

### 编码与检查规范

- Python：`ruff` 统一 lint 与格式化；`mypy` 严格模式覆盖 `services/`。
- TypeScript：`eslint` + `prettier` + `tsc --noEmit`。
- 命名：Python 用 `snake_case`；TypeScript 变量用 `camelCase`、组件用 `PascalCase`。
- 测试：`tests/unit` 不得依赖数据库，`tests/integration` 可使用 PostgreSQL。
- 数据库迁移使用 Alembic，种子数据由独立脚本提供。
- 新增模块必须同时具备 lint、类型检查和至少一个测试入口，否则视为未完成。

## 后果

- T-01 获得明确的产出清单和可验证的完成标准。
- `design.md` 第 10 节关闭“目录结构与依赖版本”“前端框架版本”两项，遗留“模型供应商”与“Trace 导出”。
- 单 Python 项目降低 M1 构建复杂度；后续若拆分多包，需要一次迁移并另立 ADR。
- 数据库版本最终定为 17.12（Homebrew）。选择依据：本机为 macOS 13，Homebrew 已不再为该配置提供 PostgreSQL 16 的预编译包，而 14 的支持期已于 2026-11-12 结束。
- 本地 `initdb` 使用 `trust` 认证，仅限本机开发；任何非本机环境必须改用密码或证书认证。

## 拒绝的方案

- 多 Python 包 workspace：M1 的模块数量不足以抵消构建与依赖管理成本。
- 不锁依赖版本：不同会话会装出不同环境，违背可回归要求。
- 用现成 Agent 框架承载业务状态：与 ADR-0001 和 `overview.md` 第 7 节冲突。
