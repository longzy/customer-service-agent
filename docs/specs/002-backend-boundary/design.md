# R0-2 设计：后端模块边界

- 状态：已批准
- 批准：2026-11-16（用户确认 R0-2 规格与任务地图）
- 日期：2026-11-16
- 关联：[requirements.md](requirements.md)、[tasks.md](tasks.md)、[ADR-0005](../../adr/0005-enterprise-boundary.md)
- 目的：在不改变行为的前提下完成模块解耦，为 M1 留出稳定 seam

## 1. 设计原则

- `services/api` 只做 HTTP：路由、中间件、DTO、依赖装配。
- 领域规则放 `domain`，员工身份放 `identity`，基础设施放 `platform`，外部系统放 `adapters`。
- `tools`/`workflows` 只依赖端口与领域类型，不依赖 HTTP 层或具体 Adapter。
- 行为冻结优先于目录整洁；任何改变 OpenAPI/DB schema 的移动都必须停止。
- 依赖规则由脚本执行，不靠评审记忆。

## 2. 目标目录

```text
services/
  api/                      # FastAPI 路由、中间件、DTO、装配
    auth_web.py             # resolve_identity/current_identity（FastAPI 专用）
  platform/                 # settings、db、SQLAlchemy models、observability、outbox
  identity/                 # Identity、ACCOUNTS、session store、RBAC 占位；不依赖 FastAPI
  domain/                   # orders、cancellation、errors（纯领域）
  adapters/
    oms/
      port.py               # OmsPort、OmsAccess、端口错误约定
      mock.py               # MockOmsAdapter + FaultEngine + fixtures
      http.py               # HttpOmsAdapter
      factory.py            # build_oms(settings)
  tools/                    # gateway、query、cancel、policy
  workflows/                # cancel
  agent_runtime/            # 已无 api/mock_oms 依赖，保持
```

与 R0-1 架构树的差异：新增 `services/domain/`，`platform/models.py` 暂存 SQLAlchemy 模型。R0-2 收口时同步更新 `docs/architecture/overview.md`。

## 3. 依赖矩阵

| 模块 | 允许依赖 | 禁止依赖 |
|---|---|---|
| `api` | `platform`、`identity`、`domain`、`adapters`、`tools`、`workflows`、`agent_runtime` | 无（入口层） |
| `platform` | 标准库、SQLAlchemy、pydantic | `api`、`identity`、`domain`、`adapters`、`tools`、`workflows` |
| `identity` | `platform`、标准库 | `api`、`domain`、`adapters`、`tools`、`workflows`、FastAPI |
| `domain` | 标准库、pydantic | `api`、`platform`、`identity`、`adapters`、`tools`、`workflows`、SQLAlchemy |
| `adapters/oms` | `domain`、`platform`、`contracts`、`errors`、httpx | `api`、`tools`、`workflows` |
| `tools` | `domain`、`identity`、`platform`、`adapters.oms.port`、`contracts`、`errors` | `api`、`mock_oms`、`adapters.oms.mock`、`adapters.oms.http` |
| `workflows` | `domain`、`identity`、`platform`、`tools` | `api`、`mock_oms`、具体 Adapter |
| `agent_runtime` | `domain`、`contracts`、`platform`、`identity`（仅类型） | `api`、`mock_oms`、SQLAlchemy、FastAPI、具体 Adapter |

`api/admin_routes.py` 是开发/测试专用的故障注入入口，允许引用 `adapters.oms.mock.FaultEngine`；生产不注册该路由。

## 4. 访问上下文与 OmsPort

### 4.1 OmsAccess

```python
@dataclass(frozen=True)
class OmsAccess:
    tenant_id: str
    user_id: str | None = None
    verified_order_ids: frozenset[str] = frozenset()
```

- 员工路径：`user_id` 非空，按 `(tenant_id, user_id)` 判归属。
- 匿名客户路径（M1）：`user_id=None`，`verified_order_ids` 来自当前会话的订单号 + 手机尾号校验结果。
- R0-2 只实现员工路径；匿名路径只保证类型可承载，不实现校验与 session。

### 4.2 OmsPort

```python
class OmsPort(Protocol):
    def is_visible(self, access: OmsAccess, order_id: str) -> bool: ...
    def get_order(self, access: OmsAccess, order_id: str) -> dict[str, Any]: ...
    def list_recent_orders(self, access: OmsAccess, limit: int) -> list[dict[str, Any]]: ...
    def submit_cancel(self, access: OmsAccess, order_id: str, idempotency_key: str) -> str: ...
    def get_cancel_result(self, tenant_id: str, idempotency_key: str) -> str: ...
```

- `is_visible` 取代 `OwnershipIndex`，成为网关的归属闸门；Mock 本地判定，Http 走只读归属投影。
- `get_cancel_result` 只按租户 + 幂等键查询，与当前行为一致。
- 端口错误沿用现有类型：`OrderNotFound`、`CancelRejected`、`IdempotencyConflict`、`DownstreamInvalidResponse`，以及内置 `TimeoutError` 与 `ConnectionError`；不新增异常类。
- 不做内部重试；重试仍由 Tool Gateway/Workflow 负责。
- `limit=0` 返回空列表；负数由 Tool Schema 拒绝，Adapter 收到负数时抛 `ValueError`。
- `get_cancel_result` 的合法状态为 `ACCEPTED`、`CANCELLED`、`REJECTED`、`UNKNOWN`；`UNKNOWN` 是结果不是错误。

### 4.3 ToolGateway 改动

`ToolGateway` 的 `ownership: OwnershipIndex` 改为 `oms: OmsPort`，授权检查调用 `oms.is_visible(access, order_id)`。`OmsAccess` 由 `Identity` 构造：

```python
def access_of(identity: Identity) -> OmsAccess:
    return OmsAccess(tenant_id=identity.tenant_id, user_id=identity.user_id)
```

`services/tools/gateway.py` 不再 import `services.api.*`；`OwnershipIndex` 删除或移入 Mock Adapter 内部。`scripts/verify.sh` 的 `prod import` 冒烟改为导入 `services.api.main`、`services.tools.gateway` 与 `services.adapters.oms.factory`，不再构造 `OwnershipIndex`。

## 5. Adapter 与 factory

### 5.1 MockOmsAdapter

- 从 `services/mock_oms/service.py`、`faults.py`、`fixtures/` 迁入 `services/adapters/oms/mock.py` 与 `services/adapters/oms/fixtures/`。
- 类名 `MockOmsAdapter`，保留故障注入：`delay`、`timeout`、`unavailable`、`invalid_response`、`lost_response`。
- `is_visible` 使用本地夹具归属；不调用外部服务，保持 001 规格 AC-02“未授权不触达 OMS”的语义。
- `admin_routes` 通过 `app.state.oms` 取 `MockOmsAdapter`，只在开发/测试注册。

### 5.2 HttpOmsAdapter

- 使用 `httpx.Client`，`timeout=settings.oms_timeout_seconds`；构造函数接受可选 `client`，测试注入 `httpx.Client(transport=httpx.MockTransport(handler))`。
- 外部传入的 client 由调用方关闭；Adapter 不关闭注入的 client。
- 约定最小 HTTP 契约（真实 OMS 接入前由 ADR 复审）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/orders/{order_id}` | 返回 OrderDetail JSON；404 → `OrderNotFound` |
| GET | `/orders?limit=N` | 返回当前主体的订单列表 |
| GET | `/orders/{order_id}/visibility` | 返回 `{"visible": bool}`，只读归属投影 |
| POST | `/orders/{order_id}/cancellations` | body `{"idempotency_key": "..."}`，返回 `{"state": "ACCEPTED"}` |
| GET | `/cancellations/{idempotency_key}` | 返回 `{"state": "..."}` |

- 身份通过 `X-Tenant-Id`、`X-User-Id` 头传递；匿名路径的 `X-Session-Id` 留到 M1。
- 错误映射：`httpx.TimeoutException` → `TimeoutError`；`httpx.ConnectError` → `ConnectionError`；非 JSON/字段非法 → `DownstreamInvalidResponse`；404 → `OrderNotFound`；409 → `IdempotencyConflict`；其余 4xx/5xx → `ConnectionError`。
- 所有映射都不改变 API 错误封套；`ToolGateway` 继续按现有异常类型归类。
- 返回体必须过 `OrderDetail`/状态 Schema 校验，避免把非法字段带入业务层。

### 5.3 契约测试矩阵

测试文件 `tests/unit/adapters/test_oms_contract_AC_25.py`，同一组用例参数化跑 `MockOmsAdapter` 与注入 MockTransport 的 `HttpOmsAdapter`：

| 用例 | Mock 准备 | Http 准备 | 期望 |
|---|---|---|---|
| 查单成功 | 夹具订单 | 200 + OrderDetail JSON | 返回等价订单字典 |
| 列表边界 | `limit=0` | `?limit=0` 返回 `[]` | 空列表 |
| 超时 | `FaultEngine` 注入 `timeout` | handler 抛 `httpx.ReadTimeout` | `TimeoutError` |
| 非法响应 | 注入 `invalid_response` | 200 + 非 JSON 或缺字段 | `DownstreamInvalidResponse` |
| 未知结果 | `set_cancel_result(..., "UNKNOWN")` | 200 + `{"state": "UNKNOWN"}` | 返回 `"UNKNOWN"` |
| 重复幂等键 | 同 key 同订单重复提交 | 两次 200 + 同 state | 同一 state，不新建 |
| 幂等冲突 | 同 key 不同订单 | 409 | `IdempotencyConflict` |
| 未授权 | `is_visible` 为 false | `/visibility` 返回 false，`/orders/{id}` 返回 404 | `is_visible` 为 false；`get_order` 抛 `OrderNotFound` |

### 5.4 factory

```python
def build_oms(settings: Settings) -> OmsPort:
    raw = settings.oms_base_url.strip()
    if raw:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise OmsConfigError("OMS_BASE_URL 必须是 http/https 且包含 host")
        return HttpOmsAdapter(raw, timeout=settings.oms_timeout_seconds)
    if settings.environment in TEST_ENVIRONMENTS:
        return MockOmsAdapter()
    raise OmsConfigError(f"environment={settings.environment} 必须配置 OMS_BASE_URL，不能回落 Mock")
```

- `OmsConfigError` 定义在 `services/adapters/oms/factory.py`，是启动期配置错误，不进入 API 错误封套。
- `Settings` 新增 `oms_base_url: str = ""`。
- `create_app(settings_override: Settings | None = None)` 在构造时调用 `build_oms(settings_override or settings)`；测试传显式 Settings，不依赖模块级单例。
- 模块级 `app = create_app()` 保留，uvicorn 以非零退出码失败；错误只记录环境名与变量名。
- 开发/测试已有 `.env` 的 `ENVIRONMENT=development`，默认仍走 Mock。

## 6. 配置与启动

| environment | `OMS_BASE_URL` | 结果 |
|---|---|---|
| `development` / `test` | 空 | Mock Adapter |
| `development` / `test` | 合法 URL | Http Adapter |
| `development` / `test` | 非法 URL | `OmsConfigError`，启动失败 |
| `production` | 空/全空白 | `OmsConfigError`，启动失败 |
| `production` | 合法 URL | Http Adapter |
| `production` | 非法 URL | `OmsConfigError`，启动失败 |
| 其他 | 空 | 按 production 失败 |
| 其他 | 合法 URL | Http Adapter |
| 其他 | 非法 URL | `OmsConfigError`，启动失败 |

错误信息只包含环境名与变量名，不打印任何密钥或完整 URL 凭据。

## 7. check-imports 规则与基线

### 7.1 规则

| ID | 源 | 禁止 |
|---|---|---|
| R1 | `services/agent_runtime`、`services/tools`、`services/workflows` | `services.api` |
| R2 | `services/tools`、`services/workflows` | `services.mock_oms`、`services.adapters.oms.mock`、`services.adapters.oms.http` |
| R3 | `services/domain` | `services.api`、`services.platform`、`services.identity`、`services.adapters`、`services.tools`、`services.workflows`、`sqlalchemy`、`fastapi` |
| R4 | `services/platform` | `services.api`、`services.identity`、`services.domain`、`services.adapters`、`services.tools`、`services.workflows` |
| R5 | `services/adapters/oms` | `services.api`、`services.tools`、`services.workflows` |
| R6 | 全 `services/`（排除 `services/mock_oms/` 自身） | `services.mock_oms`（退役后不得再出现） |

### 7.2 行为

- 纯函数 `find_violations(root: Path) -> list[Violation]` 负责扫描；CLI 只是包装，`--root PATH` 同时决定扫描根与基线的路径基准。AC-22 的临时目录测试直接调用该函数。
- AST 扫描 `<root>/services/**/*.py`，统计 `Import` 与 `ImportFrom`；`TYPE_CHECKING` 与 `try/except ImportError` 同样计入。
- 相对 import 按源文件包路径解析；动态 `importlib` 不静态检测，评审时人工确认。
- 默认即严格：违规未登记在 `scripts/import-baseline.txt` → 退出码 1；已登记 → 提示剩余数量；登记但已无违规 → 退出码 1（禁止永久豁免）。`--strict` 是兼容别名，`verify.sh` 显式传入。
- 基线文件不存在或只有注释 → 视为空基线；`--baseline PATH` 可覆盖默认路径。
- 检查器自身异常（读文件失败、AST 解析失败）→ 退出码 2。
- `verify.sh` 增加 `== import 边界 ==`，调用 `python3 scripts/check-imports.py --strict`。
- R0-2 出口时 `scripts/import-baseline.txt` 只保留注释，有效条目数为 0。

### 7.3 全局 AC 编号门禁

`tests/unit/test_naming_convention.py` 当前只解析 `001-order-cancel` 的需求文档，会把 AC-22~29 判成不存在。T-22 必须把它改为扫描 `docs/specs/*/requirements.md` 的并集，并断言并集非空、编号不重复。

## 8. 迁移顺序

1. **T-22 检查器、快照与命名门禁**：`find_violations(root)`/CLI/基线；更新 `test_naming_convention.py` 覆盖全部规格；在任何移动之前捕获 OpenAPI 与 DB metadata 快照；接入 `verify.sh`。
2. **T-23 共享模块迁移**：一次迁 `platform`（settings/db/models/observability）、`identity`（纯身份/session）、`domain`（orders/cancellation/errors）；FastAPI 中间件拆到 `api/auth_web.py`；`api`/`tools`/`workflows` 改 import。
3. **T-24 OMS 端口与 Mock**：定义 `OmsPort`/`OmsAccess`，迁 `MockOmsAdapter` 与夹具，`ToolGateway` 改用端口授权，建立 Mock/Http 共用契约测试。
4. **T-25 Http 与 factory**：实现 `HttpOmsAdapter`（可注入 client）、URL 校验、`build_oms`、`create_app(settings)` 与生产启动失败。
5. **T-26 收口**：重接 `api`，删除 `services.mock_oms` 与 `services.api.domain`，基线清零，更新 `verify.sh` 的 `prod import` 冒烟。
6. **T-27 行为冻结**：显式导入 `platform.models` 后建立 DB metadata 快照对比，并建立 OpenAPI 对比测试、跑全量回归。
7. **T-28 文档与回滚**：更新 `overview.md`、执行回滚演练并记录 SHA/命令/退出码。

T-23 依赖 T-22；T-24 依赖 T-23；T-25 依赖 T-24；T-26 依赖 T-23–T-25；T-27/T-28 依赖 T-26。

## 9. 行为冻结证据

- **OpenAPI**：在 T-22 任何文件移动之前，由 `create_app(settings_fixture).openapi()` 生成 `tests/fixtures/openapi-r0-2.json`；T-27 比较路由、方法、状态码与 schema。
- **DB schema**：同样在 T-22 移动之前，显式导入 `services.api.models` 后由 `Base.metadata` 生成 `tests/fixtures/db-schema-r0-2.json`；T-27 先导入 `services.platform.models`，断言表数 > 0，再比较表、列、类型、可空、主键。
- **现有测试**：413 个测试数量不减少；只允许改 import 路径，不允许改断言语义。
- **路由覆盖**：`scripts/check-route-coverage.py` 结果不变。
- **场景评测**：`evals/run.py` 报告不变。

若 OpenAPI/DB 快照意外变化：停止 T-26，回到设计判断是“必须接受的契约变化”还是“移动引入的回归”。R0-2 默认不接受任何变化。

## 10. 回滚方案

- R0-2 不包含数据库迁移，回滚只需 revert 代码提交。
- 回滚对象：R0-2 起点 SHA（R0-1 关闭时的 `main` HEAD）到 R0-2 结束 SHA。
- 演练：在临时分支执行 `git revert --no-commit <start>..<end>`，解决冲突后运行 `./scripts/verify.sh --no-record`，记录两个 SHA、命令与退出码，全绿后丢弃该分支。
- 若线上已切换 Http Adapter，回滚配置为 `OMS_BASE_URL=` 且 `ENVIRONMENT=development` 仅用于本地；生产回滚需恢复上一版本配置，不允许静默回落 Mock。

## 11. 风险与未决

| 风险 | 缓解 |
|---|---|
| 移动 Pydantic 模型导致 OpenAPI 组件名变化 | 快照测试；必要时固定 `title`，仍失败则停止并评审 |
| 33 个测试文件、85 处 `services.api` 引用 | 按任务分批改 import；不改断言 |
| Http Adapter 契约是暂定，真实 OMS 未知 | 标记为 R0-2 约定契约；真实接入前另立 ADR |
| 基线可能变成永久豁免 | 过期基线即失败；R0-2 出口只保留注释，有效条目为 0 |
| `admin_routes` 依赖 Mock 故障注入 | 仅开发/测试注册；生产不暴露 |
| 动态 import 绕过检查 | 规则禁止；评审检查 `importlib` 用法 |
