# 开发流程

- 状态：已批准
- 批准：2026-11-17（用户确认替换 S0–S8；规范先行，样板后做）
- 适用：本仓库全部变更；人类与 AI Agent 同权
- 关系：[工程标准](standards.md) 定义“什么算合格”；[架构不变量](../architecture/invariants.md) 定义“什么不能破”；[当前状态](../CURRENT.md) 是唯一状态视图

## 0. 一页速览

```text
Frame（目标/非目标/完成标准）
  -> Plan（1–3 页方案与取舍）
  -> Build & Verify（一次一个垂直 feature）
  -> Review & Ship（代码评审 + 人工走查）
```

三句话：**风险决定仪式；测试/演示是门禁；文档只记录决策与契约。**

## 1. 原则

| ID | 原则 | 反例 |
|---|---|---|
| P-1 | 风险配比：不可逆/高权限才重流程 | 改文案与改权限走同一套评审 |
| P-2 | 验证优先：能自动判定的不靠人记 | 卡里写“已验证”，没有命令 |
| P-3 | 单一事实源：一处写入，其余派生 | 4 份手写状态副本 |
| P-4 | 人决策、AI 执行：人定目标/取舍，AI 探索/实现/验证 | 让 reviewer 猜产品方向 |
| P-5 | 规则预算：新增必须替换或删除 | 同一规则在 3 份文档重复 |

## 2. 风险分级

按**单个变更/单个 feature**定级，不按整个里程碑继承最高级。

| 级别 | 判据（满足任一） | 产物 | 评审 |
|---|---|---|---|
| T0 | 注释、措辞、格式、补丁 | 无 | 自审 |
| T1 | 单个可观察行为，不动契约/迁移/权限/依赖 | brief/plan 可合并为一段 | 1 人代码评审 |
| T2 | 跨层、契约、迁移、新依赖、新模块 | brief + plan + features | 代码评审 + 测试 |
| T3 | 权限、租户、资金、不可逆、模型/Prompt | 上述 + 威胁模型/回滚 | 独立安全评审 + 业务批准 |

## 3. 四个阶段

### 3.1 Frame

产物：`brief.md`（1 页）+ `features.md`（端到端 feature 列表）。

必须写：

- 问题、目标、非目标；
- 2 分钟用户故事：谁、看到什么、发生什么；
- done-when：测试/演示/指标；
- 风险级别与理由；
- feature 列表：每条是穿过 DB/API/UI/tests 的垂直路径，标明验证方式。

完成标志：**用户能复述“做什么、不做什么、怎么算完成”**。AC 表可作附录，不是 Frame 的主角。

### 3.2 Plan

产物：`plan.md`（1–3 页；复杂项目可更长）。

必须写：

- context、goals、non-goals；
- 方案与**取舍/替代方案**；
- 数据/API/状态机/并发；
- 失败路径与**用户可见文案**；
- 测试 seam、风险、回滚。

设计文档只在有歧义/有取舍时写；没有取舍的机械改动直接在 feature 里做。T3 加威胁模型、越权矩阵、回滚；评审一次，不按阶段重复评审。

完成标志：**未决项为空；每个关键决策有 why/替代方案；reviewer 能按 plan 实现。**

### 3.3 Build & Verify

- 一次只做一个 feature；先写失败测试，再实现；
- 每完成一个 feature，更新 `features.md` 的 `passes`；
- 跑 `./scripts/verify.sh`；关键路径加端到端/浏览器验证；
- 提交保持小步，main 始终可运行。

完成标志：**feature 的验证命令通过；用户可演示该 feature；没有静默跳过。**

### 3.4 Review & Ship

- 独立上下文代码评审：看 diff、测试、越权/失败路径；
- 人工走查：按 brief 的 2 分钟故事走一遍；
- lasting decisions 写 ADR；更新 plan/features，不让文档腐烂；
- 发布后清理过期文档与 feature 状态。

完成标志：**代码评审通过 + 人工走查通过 + `verify.sh` 全绿。**

## 4. 产物路径

```text
docs/specs/<NNN>-<slug>/brief.md      # 1 页目标/故事/done-when
docs/specs/<NNN>-<slug>/plan.md       # 方案/取舍/契约
docs/specs/<NNN>-<slug>/features.md   # 垂直 feature + passes
docs/tasks/<spec>/T-XX.md             # 当前 feature 的执行卡
docs/reviews/<spec>/T-XX.md           # 代码评审记录
docs/adr/                             # lasting decisions
```

- 001/002 历史 spec 仍用 `requirements/design/tasks`，检查器兼容；新 spec 一律用 `brief/plan/features`。
- 不新增 `prd.md`、`spec.md`、`design-doc.md` 等平行文档。

## 5. 状态与门禁

状态：文档 `草案` → `等待评审` → `已批准`；执行卡 `待确认` → `待开工许可` → `待评审` → `已完成`。

门禁：

- G0：在 milestone 内，风险级别已定；
- G1：brief 的 done-when 可验证；
- G2：`verify.sh` 全绿；
- G3：T3 的安全评审/回滚通过；
- G4：用户走查通过。

实现者不得为自己的改动签字；代码评审用独立上下文。

## 6. 触发语

| 你说 | 产出 |
|---|---|
| “开工” | 当前已批准 feature 的执行卡 + 实现 |
| “先规划” | Frame/Plan，不写代码 |
| “评审” | 独立代码评审 + 逐 feature 证据 |
| “收口” | 更新 features/CURRENT/ADR，提交 |

## 7. 停止并请求决策

- 能力不在当前 Milestone；
- 改状态机、权限、租户、核心架构；
- 引入生产基础设施/付费服务/真实业务系统；
- 与宪章、ADR、验收冲突；
- 证据不足且错误代价涉及资金、隐私、合规。

## 附录 A：旧 S0–S8 映射

| 旧 | 新 |
|---|---|
| S0 登记/S1 规格 | Frame |
| S1.5 可判定性评审 | 并入 Frame 的 done-when 检查 |
| S2 设计 | Plan |
| S3 任务地图/S4 卡/S5 红绿 | Build & Verify |
| S6 验证/S7 盲评/S8 发布 | Review & Ship |
