# 开发流程

- 状态：已批准
- 批准：2026-11-17（用户确认替换 S0–S8；规范先行，样板后做）；2026-11-21（用户确认门禁频率：全量只在收口跑一次，评审前用定向测试）；2026-11-21（文档模型改为 requirements/design/tasks，任务状态源改为执行卡 frontmatter）；2026-11-21（用户确认 design/tasks 模板基线重构）
- 适用：本仓库全部变更；人类与 AI Agent 同权
- 关系：[工程标准](standards.md) 定义“什么算合格”；[架构不变量](../architecture/invariants.md) 定义“什么不能破”；[当前状态](../STATUS.md) 是唯一状态视图

## 0. 一页速览

```text
Frame（目标/非目标/完成标准）
  -> Plan（Context/Goals/Design/Alternatives/Cross-cutting）
  -> Build & Verify（一次一个任务）
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
| P-6 | 模板先行：模板是 schema，文档是 instance；先定模板再生成/评审文档 | 先写文档再反复改模板，文档结构随人漂移 |

## 2. 风险分级

按**单个变更/单个任务**定级，不按整个里程碑继承最高级。

| 级别 | 判据（满足任一） | 产物 | 评审 |
|---|---|---|---|
| T0 | 注释、措辞、格式、补丁 | 无 | 自审 |
| T1 | 单个可观察行为，不动契约/迁移/权限/依赖 | requirements/design 可合并为一段；不单出 tasks | 1 人代码评审 |
| T2 | 跨层、契约、迁移、新依赖、新模块 | requirements + design + tasks | 代码评审 + 测试 |
| T3 | 权限、租户、资金、不可逆、模型/Prompt | 上述 + 威胁模型/回滚 | 独立安全评审 + 业务批准 |

## 3. 四个阶段

### 3.1 Frame

前置：模板基线已定（[模板目录](../templates/README.md)、本文件 §8）；没有模板基线不写 spec。

产物：`requirements.md`（PR ≤1 页 + FAQ ≤5 页，模板 [requirements](../templates/requirements.md)）。

必须写：

- PR/FAQ：客户、问题、方案、引语（无真实访谈写“待补”，不得编造）、成功度量、非目标、备选方案；
- AC 附录：可判定、可追溯的验收编号（`scripts/trace.py` 的输入）；
- 风险级别与理由；
- 垂直切片表（可选）：切片/顺序/blocking edge；这是范围决策，不是可执行任务。

完成标志：**用户能复述“为谁、做什么、不做什么、怎么算完成”**；AC 可判定、可追溯；有垂直切片时覆盖全部 AC。

### 3.2 Plan

产物：`design.md`（T2 1–3 页，T3 按需扩展，附录不计；模板 [design](../templates/design.md)）。

必须写（Google Design Doc 五节，另列未决问题；模板 [design](../templates/design.md)）：

- Context and Scope、Goals and Non-Goals；
- The Design：模块边界、数据模型/一致性/迁移、API/状态机/并发/幂等/事务归属、失败路径；T3 加测试策略；
- Alternatives Considered：至少 1 个真实备选及不选原因；另写 Drawbacks（选了它的代价）与 Prior art（可选）；
- Cross-cutting Concerns：安全/权限/审计、可观测性/测试 seam、兼容/迁移/发布/回滚、性能/成本；T3 加威胁模型与越权矩阵；
- 未决问题：评审前清零。

设计文档只在有歧义/有取舍时写；没有取舍的机械改动直接在执行卡里做；评审一次，不按阶段重复评审。模板基线：Google Design Doc（Context/Goals/Design/Alternatives/Cross-cutting）、Rust RFC（Drawbacks/Prior art/Unresolved）、MADR（决策后果）、DoR/DoD（任务卡）。

完成标志：**未决项为空；每个关键决策有 why/替代方案；reviewer 能按 design 实现。**

#### 3.2.1 生成任务（Plan 批准后）

- 从 design 的契约与 requirements 的 AC/垂直切片派生执行卡：`docs/tasks/<spec>/F-XX.md`；
- 执行卡 frontmatter 是唯一状态源：`id`、`title`、`spec`、`milestone`、`status`、`category`、`ac`、`updated`；可选 `depends_on`（前置任务）、`slice`（垂直切片）、`risk`（覆盖默认级别）；
- 执行卡必须有 Definition of Ready（§2.1）、声明 seam（§2.3）、判定表映射（§2.5）、验证（§3）、证据（§4）、评审（§5）、Definition of Done（§6）；T2/T3 写发布与回滚（§7）；
- `make gen-tasks` 从所有执行卡生成 `docs/specs/<spec>/tasks.md`；`check-docs.py` 强制每个 AC 至少被一张执行卡引用；
- `tasks.md` 是派生索引，不要手改；覆盖或粒度不对，退回改 design/切片。

### 3.3 Build & Verify

- 一次只做一个任务；先写失败测试，再实现；验证命令与证据写执行卡第 3、4 节；
- 执行卡状态只改 frontmatter：`todo`、`doing`、`review`、`done`；不再手写 `Passes`；
- 不得改任务标题/AC 来迁就实现；要改先改 `requirements.md`/`design.md` 并重新评审；
- 关键路径加端到端/浏览器验证（多身份配方见 [浏览器走查](e2e-walkthrough.md)）；API 契约变更必须跑 `./scripts/check-contracts.sh`（verify 已包含；`check-api-types.sh` 为兼容入口）；全量 `make verify-check` 只在收口跑一次；失败则整改后重跑并做增量复审；
- 实现过程用 `make verify-changed ARGS=F-08`（按路径触发，只跑改动涉及的检查：后端 ruff/mypy/pytest、chat 或 workspace 前端、文档/状态/追溯、契约；互不牵连，`--dry-run` 可先看计划；不跑全量 pytest/评测/构建）；`make verify-check` 只留给收口；
- 全量并行实测（2026-11-21，819 条）：2 片 2:29、4 片 2:31，串行约 3:10，收益 <25%；瓶颈是单机 DB/IO 而非 CPU，因此不接门禁。全量 >5 分钟或 CI 需要分片时再评估（优先 CI 矩阵与 JUnit 合并，不改本地默认）。
- 演示数据重置统一用 `make dev-reset`，不手写 `DELETE`/`UPDATE` 修改开发库；
- 每次状态变化后运行 `make gen-tasks` 与 `make dashboard`，让索引和看板追上执行卡；
- 提交保持小步，main 始终可运行。

完成标志：**任务的验证命令通过；用户可演示该任务；没有静默跳过。**

### 3.4 Review & Ship

- 评审输入：`python3 scripts/review_pack.py F-XX` 生成评审包（固定点、diff、AC 原文、执行卡 §1/§2、design、命令）；实现尚未提交时加 `--include-worktree`，直接比较固定点与工作区；先跑 `make review-check`（机械前置），再跑绑定 AC 的定向测试；全量门禁由收口执行，评审结论以收口全量为准（全量失败则评审作废并增量复审）；
- 两轴独立评审按 [评审模板](../templates/review.md) 与 [两轴提示词](review-prompts.md) 输出；Standards 与 Spec 报告分开写，先复核门禁，再逐 AC 给证据；
- 独立上下文代码评审：看 diff、测试、越权/失败路径；
- 人工走查：按执行卡第 3、4 节逐条演示；
- lasting decisions 写 ADR；更新 requirements/design/执行卡，不让文档腐烂；
- 收口顺序：`close_feature.py --apply` → `make gen-tasks` → `make dashboard` → 更新 `STATUS.md` → `make verify` → 提交；
- 发布后清理过期文档与任务状态。

完成标志：**代码评审通过 + 人工走查通过 + `verify.sh` 全绿。**

## 4. 产物路径

```text
docs/ROADMAP.md                       # 全局：阶段与出口条件
docs/STATUS.md                        # 全局：当前状态一屏（唯一状态视图）
docs/specs/<NNN>-<slug>/requirements.md   # 需求：为什么/给谁/做什么/不做什么/成功度量/AC
docs/specs/<NNN>-<slug>/design.md         # 设计：架构/数据/API/失败/备选/横切/未决
docs/specs/<NNN>-<slug>/tasks.md          # 生成物：任务索引
docs/tasks/<spec>/F-XX.md                 # 执行卡：状态源 + 步骤 + 证据 + 回滚
docs/reviews/<spec>/F-XX.md               # 代码评审记录
docs/dashboard.html                       # 生成物：Roadmap / Board / Table
docs/status.json                          # 生成物：中立数据层
docs/adr/                                 # lasting decisions
```

- 新 spec 一律用 `requirements/design/tasks` 三件套。
- 不新增 `prd.md`、`spec.md`、`design-doc.md` 等平行文档。
- `tasks.md`、`dashboard.html`、`status.json` 是生成物，不要手改。

## 5. 状态与门禁

文档状态：`草案` → `等待评审` → `已批准`。

执行卡状态（frontmatter）：`todo`、`doing`、`review`、`done`；异常用 `blocked`。

`STATUS.md` 写法：`进行中`/`下一步` 只写未完成任务 ID；已完成 ID 只出现在 `已完成`，否则 `check-status.py` 会按状态矛盾报错。未完成任务必须出现在 `进行中` 或 `下一步`。

门禁：

- G0：在 milestone 内，风险级别已定；模板基线已定（requirements/design/tasks）；
- G1：requirements 的成功度量与 AC 可验证，且每个 AC 被执行卡 frontmatter 引用；
- G2：收口时 `verify.sh` 全绿；
- G3：T3 的安全评审/回滚通过；
- G4：按执行卡第 3、4 节走查通过。

实现者不得为自己的改动签字；代码评审用独立上下文。

## 6. 触发语

| 你说 | 产出 |
|---|---|
| “开工” | 当前已批准任务的执行卡 + 实现 |
| “先规划” | Frame/Plan，不写代码 |
| “评审” | 评审包 + 机械前置 + 两轴独立评审 + 逐任务证据 |
| “收口” | `close_feature.py --apply` → `make gen-tasks` → `make dashboard` → 更新 `STATUS.md` → `make verify` → 提交 |

## 7. 停止并请求决策

- 能力不在当前 Milestone；
- 改状态机、权限、租户、核心架构；
- 引入生产基础设施/付费服务/真实业务系统；
- 与宪章、ADR、验收冲突；
- 证据不足且错误代价涉及资金、隐私、合规。

## 8. 模板基线（2026-11-21）

- `requirements.md`：PR/FAQ + AC + 垂直切片；2026-11-21 增可选“产品决策/用户故事/判定表”，AC 用可观察语言。
- `design.md`：Google Design Doc 五节 + Rust RFC 的 Drawbacks/Prior art/Unresolved + MADR 的决策后果；新增“数据模型、一致性与迁移”“测试策略（可选）”“兼容、迁移与发布/回滚”。
- 执行卡：DoR（§2.1）、seam（§2.3）、判定表（§2.5）、测试层级、证据、DoD（§6）、T2/T3 发布与回滚（§7）；frontmatter 可选 `depends_on`/`slice`/`risk`。
- 旧执行卡不批量重写；新卡从 004 起按本模板。`check-docs.py` 兼容旧卡的第 4/5 节编号。

## 附录 A：旧 S0–S8 映射

| 旧 | 新 |
|---|---|
| S0 登记/S1 规格 | Frame |
| S1.5 可判定性评审 | 并入 Frame 的成功度量与 AC 检查 |
| S2 设计 | Plan |
| S3 任务地图/S4 卡/S5 红绿 | Build & Verify |
| S6 验证/S7 盲评/S8 发布 | Review & Ship |
