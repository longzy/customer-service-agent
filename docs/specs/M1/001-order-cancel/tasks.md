# M1 实施任务

- 状态：已批准
- 批准：2026-11-14（本次会话由用户确认）
- 性质：本文件是任务地图，负责顺序与 AC 追溯；每个任务的执行契约见 `design-cards/`。
- 修正：任务开工时允许修正描述，需在同一提交更新本文件并说明理由。
- 原则：每个任务完成时必须提供测试和验收证据

## Phase 0：契约先行

### T-01 创建工程骨架

依据：`docs/adr/0004-engineering-baseline.md`（技术栈、目录与编码规范）、`ui.md`（界面结构）。

产出：

- 根目录 `pyproject.toml` + `uv.lock`，以及 `services/{api,agent_runtime,tools,workflows,mock_oms}`、`apps/web`、`packages/contracts`、`evals/`、`tests/unit`、`tests/integration`。
- 工具链配置：ruff、mypy、pytest；eslint、prettier、tsc、vitest。
- `.env.example`、`.gitignore`；数据库使用本机 PostgreSQL 17.12（见 ADR-0004），不引入容器文件。
- 后端与前端各一个 smoke 测试，保证测试命令不会因空集合而误判通过。
- `apps/web` 只实现 `ui.md` 的空白态与输入区空壳；消息与确认逻辑留给 T-10。

完成标准（必须记录真实命令与输出，禁止照抄模板）：

- `uv run ruff check .`、`uv run mypy services`、`uv run pytest` 退出码均为 0。
- `pnpm -C apps/web lint`、`pnpm -C apps/web typecheck`、`pnpm -C apps/web test` 退出码均为 0。
- `AGENTS.md` 与 `README.md` 写入上述真实命令；`CURRENT.md` 记录验证结果。
- 两项可执行检查在本任务落地：AC 引用完整性（`scripts/check-docs.py`）与包边界不变量（`tests/unit/test_package_boundaries.py`）。

关联：不直接对应 AC，为全部 AC 提供可运行基座。

### T-02 定义统一领域类型和错误码

依据：`requirements.md` 第 6 节、`design.md` 第 3 与第 5 节、`ui.md` 第 3 节。

产出：

- `packages/contracts/schemas/`：OrderSummary、OrderDetail、CancelEligibility、CancellationState、ErrorCode 的 JSON Schema，作为唯一定义来源。
- `services/api/domain/`：与 Schema 对应的 Python 类型，不手写重复定义；模块之间只传领域类型，不传裸 `dict`。
- 状态枚举：5 个订单状态与 10 个取消任务状态；“内部状态 → 用户可见表达”的映射函数对应 `requirements.md` 第 6 节的对照表。
- 错误码：至少区分“业务拒绝”“越权”“依赖不可用”“响应非法”“内部错误”五类；每个错误码标注是否可重试、是否对用户可见。
- 契约测试：每个 Schema 一个正例与一个反例，非法输入必须被拒绝。

完成标准：

- `uv run pytest` 覆盖契约正反例并全部通过。
- 状态枚举与映射表的条目一一对应，任何状态缺少映射时测试失败。
- `uv run mypy services` 严格模式通过；跨模块调用不出现裸 `dict`。

关联：AC-02、AC-04、AC-07、AC-11、AC-16。

### T-03 定义 Tool 与 Mock OMS 契约

- `list_recent_orders`
- `get_order`
- `get_cancel_eligibility`
- `submit_cancel`
- `get_cancel_result`
- 关联：AC-01、AC-04、AC-09、AC-10。

## Phase 1：安全基础

### T-04 实现认证和租户上下文

- 可信身份注入。
- 禁止请求体覆盖租户。
- 关联：AC-02、AC-03、AC-15。

### T-05 实现授权 Tool Gateway

- Tool 白名单、输入 Schema、租户和订单归属授权。
- 统一错误与审计。
- 必须包含可执行测试：越权订单号、未知字段、非法类型的拒绝路径，且断言无业务副作用。
- 关联：AC-02、AC-03、AC-14、AC-15。

## Phase 2：业务确定性

### T-06 实现 Mock OMS

- 正常订单状态。
- 幂等取消接口。
- 故障注入：超时、重复、错误格式、成功但响应丢失。
- 关联：AC-01、AC-05、AC-09、AC-10、AC-11、AC-12。

### T-07 实现取消资格 Policy Engine

- 仅未发货且未取消允许。
- 返回原因码。
- 关联：AC-04、AC-07。

### T-08 实现 Cancellation Workflow

- 确认门禁。
- 持久化状态。
- 幂等提交。
- 未知状态查询和恢复。
- 重试耗尽转人工。
- 关联：AC-04、AC-05、AC-06、AC-09、AC-10、AC-11、AC-12、AC-13、AC-19。

## Phase 3：Agent 与交互

### T-09 实现 Agent Runtime 最小闭环

- 意图识别、订单澄清和 Tool 规划。
- 禁止直接调用写 Tool。
- 关联：AC-01、AC-08。

### T-10 实现 Web Chat

- 消息发送与会话展示。
- 确认按钮或明确确认动作。
- 人工接管入口。
- 关联：AC-04、AC-06、AC-13。

### T-11 实现结果校验和用户回复

- 对照权威状态验证模型表达。
- 统一状态语义。
- 关联：AC-16。

## Phase 4：可观测与评估

### T-12 加入 Trace 与审计

- 会话、模型、Tool、Workflow 和 OMS 调用关联。
- 敏感字段脱敏。
- 关联：AC-17、AC-18。

### T-13 建立场景评测

- 覆盖 AC-01 至 AC-19。
- 输出场景级通过率和失败节点。
- 关联：AC-01 至 AC-19（评测集覆盖全部用例）。

## 完成顺序

```text
T-01 -> T-02 -> T-03
  -> T-06
  -> T-04 -> T-05
  -> T-07 -> T-08
  -> T-09 -> T-10 -> T-11
  -> T-12 -> T-13
```

T-06 提到 T-04 之前：Mock OMS 与故障注入只依赖 T-03 的契约，先建好它，后续每个业务任务都能立刻验证异常路径。AC-09 至 AC-12 的端到端验证仍在 T-08。

