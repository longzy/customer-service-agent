# 常见变更配方（触点清单）

- 状态：已批准（2026-11-22，随 F-31 复盘补充）
- 用途：先按变更形状查“改哪里”，再打开具体文件；不替代 `overview.md` 的边界定义。
- 指针：[总体架构](overview.md) 定义分层与模块约束；本文件只列触点与验证命令。

## 1. 新增客户写路由

以 F-31 取消为例：

| 触点 | 改什么 |
|---|---|
| `backend/conversations/customer_http.py` | 路由、依赖（`CurrentCustomer`/`Db`）、错误映射、响应模型 |
| `backend/conversations/<domain>.py` | 业务编排；只 `flush`，不 `commit` |
| `backend/conversations/schemas.py` | 请求/响应 DTO，`extra="forbid"` |
| `backend/platform/models.py` + `migrations/versions/` | 新表/列与只加法迁移 |
| `backend/domain/errors.py` | 仅新增错误码时；随后 `make gen-contracts` |
| `backend/api/main.py` | 仅新增网关/装配时 |
| `backend/adapters/oms/mock.py` | 仅验收需要的 Mock 行为 |
| `tests/integration/test_<spec>_AC_XX.py` | 主路径、权限、失败、幂等 |
| `tests/unit/` | 确定性领域/工作流逻辑 |
| `apps/<app>/features/<feature>/` | 请求函数、hook、组件；类型来自生成物 |
| `docs/tasks/<spec>/F-XX.md` | §1 触点、§2.5 判定表、§4 证据 |

- 身份只来自认证依赖；正文出现 `tenant_id`/`user_id` 一律拒绝。
- 写请求用 `get_session`（路由只 `flush`）；独立事务（限速、安全审计、Trace）必须新开 session。
- 复用旧 Workflow 时显式关闭其内部提交：`SqlCancellationRepository(commit_on_save=False)`。
- 验证：`./scripts/test-db.sh tests/integration/test_<spec>_AC_XX.py -q`、`make verify-changed ARGS=F-XX`、改了契约再 `make gen-contracts`。

## 2. 新增迁移与契约派生物

1. `migrations/versions/00xx_<slug>.py`：只加法；`down_revision` 指当前 head。
2. 同步 `backend/platform/models.py`（列、索引、谓词与迁移一致）。
3. 迁移回滚测试放进 `tests/integration/test_migrations.py`。
4. 改了错误码/路由/DTO：`make gen-contracts`（生成 OpenAPI、两份 `api-types.ts`、两份测试快照）。
5. 验证：`./scripts/test-db.sh tests/integration/test_migrations.py -q`、`./scripts/check-contracts.sh`。

## 3. 复用旧 Workflow

- 先读模块 docstring 与 `CancellationRepository` 协议，确认提交归属。
- 请求级 UoW：仓储 `commit_on_save=False`；启动恢复继续用独立 session 自行提交。
- 审计：请求内事件写 `service_audit_events`；旧 `audit_events` 只保留启动恢复。
- 不复制状态机；新增入口只做归属/资格/确认来源的编排。
- 验证：`tests/unit/workflows/` 与 `tests/integration/test_cancellation_repository.py`。

