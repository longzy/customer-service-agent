# R0-2 任务地图：后端模块边界

- 状态：已批准
- 批准：2026-11-16（用户确认 R0-2 规格与任务地图）
- 日期：2026-11-16
- 输入：[requirements.md](requirements.md)、[design.md](design.md)
- 约束：每个任务一个可独立验证的切片；开工前产出 `docs/tasks/002-backend-boundary/T-XX.md`，完成后评审写入 `docs/reviews/002-backend-boundary/`
- 行为冻结：不改 HTTP 契约、DB schema、Tool 契约、Policy 与 Workflow 状态机
- AC 编号：全局唯一，本规格使用 AC-22~29

## Phase 1: 边界检查器与基线

**Goal**：先让边界与行为快照可判定，再搬代码。

- [x] T-22 建立 `check-imports.py`（`find_violations(root)` + `--root/--baseline/--strict`）与初始基线；更新全局 AC 命名门禁；在任何移动之前捕获 OpenAPI 与 DB 快照；接入 `verify.sh`
  - 文件：`scripts/check-imports.py`、`scripts/import-baseline.txt`、`scripts/verify.sh`、`tests/unit/test_naming_convention.py`、`tests/unit/test_import_rules_AC_22.py`、`tests/unit/test_verify_wiring.py`、`tests/fixtures/openapi-r0-2.json`、`tests/fixtures/db-schema-r0-2.json`
  - _验收: AC-22_

**Checkpoint**：`check-imports --strict` 对当前树报出已知违规并登记；命名门禁能识别 AC-22~29；其余检查全绿。

## Phase 2: 共享模块拆分

**Goal**：把 `backend/api` 中的基础设施、身份与领域类型迁出。

- [x] T-23 迁移 platform（settings/db/models/observability）、identity（纯身份/session）、domain（orders/cancellation/errors）；FastAPI 中间件拆到 `api/auth_web.py`；更新 `api`/`tools`/`workflows` 与测试的 import
  - 文件：`backend/platform/`、`backend/identity/`、`backend/domain/`、`backend/api/auth_web.py`、`backend/tools/`、`backend/workflows/`、`tests/unit/test_import_boundaries_AC_23.py`、相关测试
  - _验收: AC-23_

**Checkpoint**：`agent_runtime`/`tools`/`workflows` 不再 import `backend.api`；基线中 R1 条目清零。

## Phase 3: OMS 端口与 Mock

**Goal**：业务模块只依赖端口。

- [x] T-24 定义 `OmsPort`/`OmsAccess`，迁移 `MockOmsAdapter` 与夹具，`ToolGateway` 改用端口授权；建立 Mock 契约测试骨架（Http 在 T-25 接入）
  - 文件：`backend/adapters/oms/port.py`、`backend/adapters/oms/mock.py`、`backend/adapters/oms/fixtures/`、`backend/tools/gateway.py`、`backend/tools/query.py`、`backend/tools/cancel.py`、`tests/unit/adapters/test_oms_contract_AC_25.py`、相关测试
  - _验收: AC-24_

**Checkpoint**：Mock 契约骨架建立；`tools`/`workflows` 不再直接依赖具体 Adapter；Http 等价性在 T-25 判定。

## Phase 4: Http 与 factory

**Goal**：生产缺配置不回落 Mock。

- [x] T-25 实现 `HttpOmsAdapter`（可注入 client）、URL 校验、`build_oms`、`create_app(settings)` 与生产启动失败；把 Http 接入共用契约矩阵
  - 文件：`backend/adapters/oms/http.py`、`backend/adapters/oms/factory.py`、`backend/api/main.py`、`backend/platform/settings.py`、`tests/unit/adapters/test_oms_contract_AC_25.py`、`tests/unit/adapters/test_oms_factory_AC_26.py`
  - _验收: AC-25、AC-26_

**Checkpoint**：production 空/空白/非法 URL 启动失败；development 空配置走 Mock；production 合法 URL 走 Http。

## Phase 5: 收口

**Goal**：删除旧路径，清零基线。

- [x] T-26 收口核验：确认旧 `api/domain` 与 `mock_oms` 包已由 T-23/T-24 删除、基线为 0、`verify.sh` 的 prod import 自包含、API 不再接旧路径
  - 文件：`scripts/import-baseline.txt`、`scripts/verify.sh`、`tests/unit/test_import_boundaries_AC_24.py`、`docs/CURRENT.md`
  - _验收: AC-23、AC-24_

**Checkpoint**：`check-imports --strict` 退出 0；`backend.mock_oms` 不再存在；`verify.sh` 不依赖 `OwnershipIndex`。

## Phase 6: 行为冻结证据

**Goal**：证明移动没有改变契约。

- [x] T-27 建立 OpenAPI 与 DB metadata 对比测试（使用 T-22 捕获的快照），显式导入 `platform.models` 并断言表数 > 0；跑全量回归
  - 文件：`tests/unit/test_contract_snapshot_AC_27.py`、`tests/unit/test_db_schema_AC_28.py`
  - _验收: AC-27、AC-28_

**Checkpoint**：OpenAPI 与 DB schema 与重构前一致；413 个测试全过。

## Phase 7: 文档与回滚

**Goal**：文档与实际目录一致，回滚可复现。

- [x] T-28 更新 `overview.md` 目标树，执行 R0-2 起点 SHA 到结束 SHA 的 revert 演练并记录命令/退出码
  - 文件：`docs/architecture/overview.md`、`docs/reviews/002-backend-boundary/T-28.md`
  - _验收: AC-29_

**Checkpoint**：文档与目录一致；回滚演练全绿并有记录。

## 依赖与并行

```text
T-22 -> T-23 -> T-24 -> T-25 -> T-26 -> T-27 -> T-28
```

- T-23 依赖 T-22；T-24 依赖 T-23；T-25 依赖 T-24；T-26 依赖 T-23–T-25。
- T-27/T-28 依赖 T-26；T-28 的回滚演练在 T-27 快照通过后执行。
- 不并行搬模块：半迁移状态会让 import 边界与快照都不可判定。

## 完成定义

- 每条 AC 有测试或命令证据，且 `trace.py --strict` 无缺口（基线清零）。
- `import-baseline.txt` 只保留注释，`check-imports --strict` 退出码 0。
- OpenAPI 与 DB schema 快照与重构前一致。
- 现有 413 个测试全过；只改 import 路径，不改断言语义。
- 独立评审通过，用户批准；R0-2 关闭后更新 `CURRENT.md`。
