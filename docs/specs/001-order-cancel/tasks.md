# Tasks: 订单查询与未发货订单取消

- 状态：已批准
- 批准：2026-11-15（用户确认，含测试账号登录页与 AC-20）
- **Input**：`docs/specs/001-order-cancel/requirements.md`、`design.md`
- **Prerequisites**：需求与设计均已批准；任务按用户故事分组，每个故事可独立实现与测试
- **Tests**：按 `docs/process/tdd.md`，测试与实现同属一个任务，先红后绿；不为测试单列任务
- **执行卡与评审**：任务开工前产出 `docs/tasks/001-order-cancel/T-XX.md`；完成后评审记录写入 `docs/reviews/001-order-cancel/T-XX.md`

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可与同阶段其他任务并行（不同文件、无依赖）
- **[Story]**：任务所属用户故事，如 `[US1]`
- 描述包含精确文件路径；`_验收:` 行标注对应 AC

## Phase 1: Setup

**Purpose**：工程初始化与基本结构

- [x] T01 创建工程骨架（`pyproject.toml`、`services/`、`apps/web/`、`tests/`、`scripts/`）— 已完成，见 `docs/tasks/001-order-cancel/T-01.md`
- [x] T02 定义领域类型与 JSON Schema（`services/api/domain/`、`packages/contracts/schemas/`）— 已完成，见 `docs/tasks/001-order-cancel/T-02.md`
  - _验收: AC-02、AC-04、AC-07、AC-11、AC-16_

## Phase 2: Foundational（阻塞所有故事）

**Purpose**：任何用户故事开工前必须完成的基础设施

- [x] T03 定义 5 个 Tool 契约（`packages/contracts/tools/*.json`）
  - _验收: AC-01、AC-02、AC-04、AC-05、AC-07、AC-09、AC-10、AC-11_
- [ ] T04 [P] 实现认证与租户上下文（`services/api/auth.py`、`services/api/middleware.py`）
  - _验收: AC-02、AC-03、AC-15_
- [ ] T05 实现授权 Tool Gateway（`services/tools/gateway.py`）— depends on T03、T04
  - _验收: AC-02、AC-03、AC-14、AC-15_
- [ ] T06 实现 Mock OMS 与故障注入（`services/mock_oms/`）— depends on T03
  - _验收: AC-01、AC-05、AC-09、AC-10、AC-11、AC-12_

**Checkpoint**：基础设施就绪，可以开始任一用户故事。

## Phase 3: US-00 建立会话（P1）

**Goal**：用户能选择测试账号进入系统，并在租户之间切换
**Independent Test**：打开未登录页面，选择租户 A 的账号，验证会话与身份；再切换到租户 B，验证授权随之变化

- [ ] T16 [P] [US0] 实现测试账号登录页（`apps/web/app/login/page.tsx`、`apps/web/components/LoginPanel.tsx`）— depends on T04
  - _验收: AC-20_

**Checkpoint**：登录与账号切换可独立演示，后续展示均从真实会话开始。

## Phase 4: US-01/02 查询订单与最近订单（P1、P2）

**Goal**：用户能查询本人订单或最近订单，越权与非法参数被拒绝
**Independent Test**：用夹具订单调用查询接口，验证返回、越权拒绝与零写操作

- [ ] T09 [P] [US1] 实现查询意图识别与订单澄清（`services/agent_runtime/intent.py`）— depends on T05
  - _验收: AC-01、AC-08_
- [ ] T10 [P] [US1] 实现查询结果展示与空态（`apps/web/components/QueryView.tsx`）— depends on T09
  - _验收: AC-01_

**Checkpoint**：查询切片可独立演示。

## Phase 5: US-03 取消未发货订单（P1）

**Goal**：用户确认后安全取消；重复提交为 0；超时能恢复
**Independent Test**：对可取消订单走完“请求 → 确认 → 提交”，并注入超时验证恢复

- [ ] T07 [P] [US3] 实现取消资格 Policy Engine（`services/tools/policy.py`）— depends on T03
  - _验收: AC-04、AC-07_
- [ ] T08 [US3] 实现 Cancellation Workflow（`services/workflows/cancel.py`）— depends on T06、T07
  - _验收: AC-04、AC-05、AC-06、AC-09、AC-10、AC-11、AC-12、AC-19_
- [ ] T14 [P] [US3] 实现确认卡片与终态界面（`apps/web/components/ConfirmCard.tsx`）— depends on T10、T08
  - _验收: AC-04、AC-05、AC-06、AC-13、AC-16、AC-19_

**Checkpoint**：取消主流程可独立演示。

## Phase 6: US-04、US-05、US-06 解释、恢复与人工（P2、P1、P2）

**Goal**：不可取消有明确原因；未知状态可恢复；可转人工且上下文完整
**Independent Test**：对已发货订单、注入超时、连续故障分别验证三类结果

- [ ] T11 [US5] 实现结果校验与用户回复（`services/agent_runtime/validator.py`）— depends on T08
  - _验收: AC-10、AC-11、AC-16_
- [ ] T15 [US6] 实现人工转接上下文（`services/api/handoff.py`）— depends on T08、T14
  - _验收: AC-13_

**Checkpoint**：全部用户故事可独立验证。

## Phase 7: Polish & Cross-Cutting

**Purpose**：跨故事的横切质量

- [ ] T12 [P] 加入 Trace 与审计（`services/api/observability.py`、`services/api/audit.py`）
  - _验收: AC-17、AC-18_
- [ ] T13 建立场景评测（`evals/`）— depends on T10、T14、T11、T15、T12
  - _验收: AC-01 至 AC-20_

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（T01、T02）**：已完成
- **Foundational（T03 至 T06）**：依赖 Setup，**阻塞所有用户故事**
- **User Stories（Phase 3 至 6）**：依赖 Foundational 完成
  - US-00 登录最先完成，为其他故事提供真实会话
  - US-01/02 查询与 US-03 取消可并行；US-05 依赖 US-03 的 Workflow
  - US-06 人工转接依赖 US-03 的确认界面
- **Polish（T12、T13）**：依赖全部故事完成

### Within Each User Story

- 契约与类型先于实现；实现先于界面
- 每个任务先写失败测试，再写最小实现（见 `docs/process/tdd.md`）
- 一个故事完成并独立验证后，再进入下一个优先级

### Parallel Opportunities

- T04 可与 T03 并行
- T07 与 T09 可并行（不同文件）
- T10 与 T12 可并行（前后端不同文件）
- 同一故事内的模型与组件任务在无依赖时标 `[P]`

## Implementation Strategy

### MVP First

1. 完成 Setup 与 Foundational
2. 完成 US-00 登录页，确保后续演示从真实会话开始
3. 完成 US-01/02 查询切片并独立验证
4. 完成 US-03 取消切片并独立验证
5. 补齐 US-04 至 US-06 的表达、恢复与人工路径

### Incremental Delivery

每个切片完成后都能演示：查询可用 → 取消可用 → 异常可恢复 → 人工可接管 → 场景可回归。

## Notes

- `[P]` 表示不同文件、无依赖，可并行
- `[USx]` 用于追溯任务与用户故事
- 每个任务开工前必须有执行卡；完成的判定见 `docs/process/sdd.md` 第 3 节
- 执行卡与评审记录分别位于 `docs/tasks/001-order-cancel/` 与 `docs/reviews/001-order-cancel/`
