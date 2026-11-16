# R0-2 需求：后端模块边界

- 状态：等待评审
- 日期：2026-11-16
- 级别：T2（结构性；不改 API 行为）
- 依据：[ADR-0005](../../adr/0005-enterprise-boundary.md)、[总体架构](../../architecture/overview.md)、[企业化方向重置](../../initiatives/2026-11-16-enterprise-reset.md)
- 关联：[design.md](design.md)、[tasks.md](tasks.md)
- AC 编号：全局唯一；`001-order-cancel` 已使用 01–21，本规格从 22 起。
- S1.5：可判定（2026-11-16，见 `docs/reviews/2026-11-16-r0-2-spec-review.md`），待用户批准。

## 1. 目标

在不改变任何 HTTP 行为、数据库 schema 和现有验收结果的前提下：

- 把原型期集中在 `services/api` 的共享代码拆到 `platform`/`identity`/`domain`/`adapters`；
- 用 `scripts/check-imports.py` 把依赖方向变成 CI 可判定规则；
- 用 `OmsPort` 隔离 OMS，生产缺配置时启动失败，不静默回落 Mock；
- 为 M1 的员工登录、匿名客户与坐席工作台留出稳定边界。

## 2. 非目标

- 不实现新 M1 功能：员工登录/RBAC、匿名客户会话、队列、接管、工作台。
- 不改 HTTP 路由、状态码、响应体、Cookie 与 session 语义。
- 不改数据库表结构与迁移。
- 不改 Tool 契约、Policy 规则与 Workflow 状态机。
- 不接入真实 OMS；Http Adapter 只按本规格约定实现，并用假传输测试。
- 不拆微服务，不引入消息中间件。

## 3. 用户故事

### US-01 维护者：越界依赖在 CI 被拦截

作为维护者，我希望新增的越界 import 立即失败，并指出文件与模块，以便边界不随功能开发退化。

- 独立测试：在临时目录构造 `tools -> services.api` 的 import，运行检查器，断言失败。
- 验收：AC-22、AC-23、AC-24、AC-29

### US-02 部署者：生产缺 OMS 配置时启动失败

作为部署者，我希望生产环境没有 OMS 配置就启动失败，以便不会静默使用 Mock。

- 独立测试：production + 空 `OMS_BASE_URL` 调用 factory，断言抛出配置错误；development 空配置返回 Mock。
- 验收：AC-26

### US-03 开发者：只依赖端口即可替换 OMS

作为开发者，我希望 tools/workflows 只依赖 `OmsPort`，以便 Mock 与真实 OMS 可替换。

- 独立测试：同一组契约测试分别跑 Mock 与 Http Adapter。
- 验收：AC-25

### US-04 评审者：重构无行为回归

作为评审者，我希望有 OpenAPI、DB schema 与现有测试的快照证据，以便确认行为冻结。

- 独立测试：快照对比 + 全量 `verify.sh`。
- 验收：AC-27、AC-28、AC-29

## 4. 功能需求

| ID | 需求（EARS） | 验收 |
|---|---|---|
| FR-01 | 当运行 `check-imports.py --root <路径>` 时，系统应报告该根下每个越界 import 的文件与模块；存在未登记违规时退出码为 1。 | AC-22 |
| FR-02 | 当 `agent_runtime`/`tools`/`workflows` 引用 `services.api` 时，检查器应失败。 | AC-23 |
| FR-03 | 当 `tools`/`workflows` 引用 `mock_oms` 或具体 OMS Adapter 时，检查器应失败。 | AC-24 |
| FR-04 | 当对 Mock 与 Http Adapter 运行同一组 `OmsPort` 契约测试时，两者应给出等价结果与等价错误。 | AC-25 |
| FR-05 | 当 `OMS_BASE_URL` 非空但不是合法 http/https URL 时，factory 与 `create_app(settings)` 应失败；当 `environment=production` 且为空或全空白时同样失败，错误包含 `OMS_BASE_URL`。 | AC-26 |
| FR-06 | 当 `environment=development/test` 且未配置 `OMS_BASE_URL` 时，factory 应返回 Mock Adapter，不要求外部服务。 | AC-26 |
| FR-07 | 当重构完成时，OpenAPI 路由、操作与 schema 应与重构前快照一致。 | AC-27 |
| FR-08 | 当重构完成时，SQLAlchemy metadata 的表与列应与重构前快照一致。 | AC-28 |
| FR-09 | 当运行 `verify.sh` 时，应执行 `check-imports.py --strict`；R0-2 出口时 `import-baseline.txt` 的有效条目数必须为 0（允许文件只含注释）。 | AC-29 |
| FR-10 | 当从 R0-2 起点 SHA 回滚时，应能 revert R0-2 的提交范围并恢复全绿；R0-2 不包含数据库迁移。 | AC-29 |

## 5. 验收标准

| AC | 场景 | 期望 | 需求 |
|---|---|---|---|
| AC-22 | 以临时目录为 `--root`，其中出现 `services/tools/x.py -> services.api.auth` | 检查器失败，输出包含文件、模块与规则 ID，退出码 1；`find_violations(root)` 可直接断言 | FR-01 |
| AC-23 | 扫描当前 `services/` 生产代码 | `agent_runtime`/`tools`/`workflows` 对 `services.api` 的 import 数为 0 | FR-02 |
| AC-24 | 扫描当前 `services/` 生产代码 | `tools`/`workflows` 对 `mock_oms` 与具体 Adapter 的 import 数为 0 | FR-03 |
| AC-25 | 同一组契约用例分别跑 Mock 与注入 `httpx.MockTransport` 的 Http Adapter | 成功、超时、非法响应、未知结果、重复幂等键五类结果与错误类型一致 | FR-04 |
| AC-26 | production 空/全空白、development/test 空、production/development 合法 URL、任意环境非法 URL | 空 production→失败；空 development→Mock；合法 URL→Http；非法 URL→失败；错误提到 `OMS_BASE_URL` | FR-05、FR-06 |
| AC-27 | 重构前后 `app.openapi()` 对比 | 路由、方法、状态码、schema 完全一致 | FR-07 |
| AC-28 | 显式导入 `services.platform.models` 后，重构前后 `Base.metadata` 对比 | 表数 > 0，且表名、列名、类型、可空、主键一致 | FR-08 |
| AC-29 | `verify.sh`、基线文件、从 R0-2 起点 SHA revert 的演练 | 检查器接入；有效基线条目为 0；记录起点/结束 SHA、命令与退出码，revert 后全绿 | FR-09、FR-10 |

## 6. 判定表

### 6.1 OMS 配置与启动

| environment | `OMS_BASE_URL` | 结果 |
|---|---|---|
| `development` / `test` | 空 | Mock Adapter，启动成功 |
| `development` / `test` | 合法 http/https URL | Http Adapter，启动成功 |
| `development` / `test` | 非空但非法 URL | 启动失败，错误指出配置非法 |
| `production` | 空或全空白 | 启动失败，错误包含 `OMS_BASE_URL` |
| `production` | 合法 http/https URL | Http Adapter，启动成功 |
| `production` | 非空但非法 URL | 启动失败，错误指出配置非法 |
| 其他值 | 空 | 按 production 处理，启动失败 |
| 其他值 | 合法 URL | Http Adapter |
| 其他值 | 非法 URL | 启动失败 |

### 6.2 依赖检查

| 情况 | 结果 |
|---|---|
| 违规且不在基线 | 失败 |
| 违规且在基线 | 通过，但提示剩余基线数 |
| 基线条目已无对应违规 | 失败（禁止基线永久豁免） |
| 基线文件不存在或只有注释 | 视为空基线；R0-2 出口允许 |
| 基线路径指向不存在的文件 | 视为空基线，不报错 |
| `TYPE_CHECKING` 内的 import | 与运行时 import 同权，计入违规 |
| `try/except ImportError` 的可选 import | 计入违规；需要例外必须写进规则并说明理由 |
| 测试目录 `tests/` | 不检查（测试可以引用旧路径做迁移验证） |

### 6.3 冲突优先级

1. 行为冻结优先于目录整洁：任何移动若改变 OpenAPI 或 DB schema，停止并回到设计。
2. 生产失败优先于开发便利：不得为了本地启动方便而允许 production 回落 Mock。
3. 显式规则优先于隐含约定：检查器报出的违规不得用注释或动态 import 绕过。

## 7. 失败与可观测

- 检查器失败：stdout 逐行输出 `文件: import 模块（规则 ID）`，stderr 汇总数量，退出码 1；`--root` 同时决定扫描根与基线路径的解析基准。
- 配置失败：启动异常信息包含 `OMS_BASE_URL` 与当前 `environment`，不打印密钥；非法 URL 指出“必须是 http/https 且包含 host”。
- Http Adapter 失败：`httpx.TimeoutException` → `TimeoutError`，连接失败/其余 4xx/5xx → `ConnectionError`，非法 JSON/字段 → `DownstreamInvalidResponse`，404 → `OrderNotFound`，409 → `IdempotencyConflict`；API 响应体不变。
- 检查器自身异常：退出码 2，不与“有违规”混淆。

## 8. 证据 seam

| 事实 | 观测点 |
|---|---|
| 依赖方向 | `scripts/check-imports.py` 的 `find_violations(root)`、CLI 输出与 `tests/unit/test_import_rules_AC_22.py` |
| OMS 契约 | `OmsPort` 契约测试（Mock/Http 共用） |
| 启动行为 | `services/adapters/oms/factory.py::build_oms(settings)`、`create_app(settings)` |
| API 行为 | `app.openapi()` 快照测试 |
| DB 结构 | 显式导入 `services.platform.models` 后的 `Base.metadata` 快照测试 |
| 回归 | `./scripts/verify.sh` |
| 回滚 | 从 R0-2 起点 SHA 的 `git revert --no-commit start..end` + `verify.sh` 记录 |
