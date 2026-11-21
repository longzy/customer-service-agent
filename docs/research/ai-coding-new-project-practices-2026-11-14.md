# AI Coding 从 0 启动新项目：最新一手资料调研

- 调研日期：2026-11-14
- 适用项目：企业级电商智能客服 Agent
- 调研方法：只采用厂商官方文档、官方仓库和官方产品文档；先打开原文核对，再提炼结论。
- 证据边界：官方资料可以证明主流工具正在形成哪些工作流共识，不能单独证明市场采用率。本文不会把某一家厂商的流程说成“唯一正确做法”。

- 历史说明：本文写于 2026-11-14，文件名与状态字段是当时约定；当前文档模型见 [WORKFLOW](../process/WORKFLOW.md)（`requirements/design/tasks` + `STATUS`）。

## 一、结论先行

AI Coding 从零启动一个项目，当前更成熟的起点不是立即让 Agent 写代码，而是先建立三层可版本化的项目控制面：

1. **项目基线**：为什么做、为谁做、范围、非目标、架构原则、安全边界和成功标准。
2. **当前交付规格**：本轮要实现的用户故事、验收条件、技术设计、接口契约和任务清单。
3. **确定性执行关卡**：测试、类型检查、构建、Lint、权限控制、审查和评估，不以模型“口头认为完成”为准。

全局设计文档不应丢弃，也不应频繁重写。更合适的做法是：

- 保留原始评审文档作为不可变的设计依据。
- 将其中稳定的结论提炼为简短的架构基线。
- 为每个里程碑派生独立规格、任务和验收用例。
- 用 `AGENTS.md` 或同类项目上下文文件声明文档读取顺序和不可违反的约束。

因此，AI Coding 的正确方向是**保留全局地图，同时为当前迭代建立施工图**，并不是从“全局设计”直接跳到“自由编码”。

## 二、主流工具的一手实践

### 1. OpenAI Codex：持久指导、先规划、可验证完成

OpenAI 官方最佳实践建议在复杂任务中先做计划，把可复用规则写入 `AGENTS.md`，并要求 Agent 创建或更新测试、运行正确的检查、审查差异，再用证据确认完成。官方给出的任务四要素是：

- Goal：要改变或构建什么。
- Context：哪些文件、文档和错误相关。
- Constraints：架构、安全和团队规范。
- Done when：完成时必须为真的可验证条件。

官方还明确建议按“一个连贯工作单元”管理会话，而不是用一个超长会话覆盖整个项目；需要的时候可以分叉或压缩上下文。

来源：

- [Best practices | OpenAI](https://learn.chatgpt.com/guides/best-practices)，访问于 2026-11-14。

`AGENTS.md` 会在工作开始前加载，并支持从全局目录到项目目录再到子目录的分层覆盖。官方建议保持简短、准确，把构建/测试命令、仓库结构、工程约定、约束和完成定义放在里面；文件过大时应引用按主题拆分的文档，而不是无限扩写。

来源：

- [Custom instructions with AGENTS.md | OpenAI](https://learn.chatgpt.com/docs/agent-configuration/agents-md)，访问于 2026-11-14。

对本项目的含义：

- 全局设计应进入仓库，而不是只停留在聊天记录。
- `AGENTS.md` 应当是索引和控制规则，不是把所有设计文档复制进去。
- “测试通过、评测通过、Trace 可核验”应替代“代码已经写完”作为完成标准。

### 2. Anthropic Claude Code：先形成规格，再给 Agent 一个可运行的检查

Anthropic 官方最佳实践明确提出，当需求还不够清楚时，可以先让 Claude 访谈开发者，直到能够写出 `SPEC.md`；随后在新会话中基于该规格实施，让构建过程从干净上下文和明确完成定义开始。

官方还建议：

- 用具体文件、现象和“修复完成”的定义减少误解。
- 让 Agent 拿到可返回 pass/fail 的检查，例如测试、构建、Lint、输出对比或截图比对。
- 要求 Agent 提供命令和输出作为完成证据。
- 用未参与实现的新审查上下文对照规格审查差异。
- 区分非确定性指令与确定性约束：`CLAUDE.md` 和提示词主要指导模型；必须每次执行的规则应放到 hooks、权限规则、沙箱、CI 或分支保护中。
- 保持 `CLAUDE.md` 简短，只写 Agent 无法从代码中直接发现、或每次都要重复发现的信息；把局部规则放到更小范围的文件，把长流程放到按需加载的 skills 中。

来源：

- [Best practices for Claude Code | Anthropic](https://code.claude.com/docs/en/best-practices)，访问于 2026-11-14。

对本项目的含义：

- “退款必须先确认、必须幂等、不能越权”不能只写在 Prompt 里。
- 业务规则、接口契约和验收用例应先于实现。
- 关键安全规则要在服务端、Tool 层和 CI 中执行，而不是指望模型永远记得。

### 3. GitHub Spec Kit：项目 Constitution + 按功能生成的规格流水线

GitHub Spec Kit 官方仓库给出的 Spec-Driven Development 最小流程是：

```text
/speckit-constitution
/speckit-specify
/speckit-plan
/speckit-tasks
/speckit-implement
/speckit-converge
```

其中 `constitution` 每个项目创建一次，用于定义代码质量、测试和可维护性原则；其余步骤按功能重复。官方要求每一步由人审阅结果后再继续，并通过 `implement` 与 `converge` 反复收敛，直到实现与规格一致。

官方仓库还明确说明，规格驱动、Bug 修复、想法评估是可选入口，而不是所有项目必须经历的固定阶段。这意味着团队应按问题类型选择流程，而不是机械套模板。

来源：

- [GitHub Spec Kit 官方仓库](https://github.com/github/spec-kit)，访问于 2026-11-14。

对本项目的含义：

- 现有全局评审可以提炼成项目的“constitution + architecture baseline”。
- 每个里程碑再生成独立的需求、设计和任务文档。
- 不要让一个巨大的规格同时覆盖全渠道、售前、售后、运营和治理；应按可交付闭环切片。

### 4. AWS Kiro：Steering 保存长期上下文，Specs 保存当前交付

Kiro 将两类文档分开：

- **Steering**：长期项目知识，例如 `product.md`、`tech.md`、`structure.md`，默认参与每次交互。
- **Specs**：当前功能的 `requirements.md`、`design.md`、`tasks.md`，覆盖需求、验收条件、架构和可跟踪任务。

Kiro 官方强调，Steering 用持久 Markdown 文件保存产品目标、技术栈、项目结构和团队约定，减少每次会话重复解释；同时建议保持文件聚焦，并像代码一样审查和定期维护。

其文档还支持按目录、文件模式和任务描述控制上下文加载，说明当前成熟方向是“分层上下文 + 按需加载”，而非把全部资料塞进每个请求。

来源：

- [Kiro Steering](https://kiro.dev/docs/steering/)，访问于 2026-11-14。
- [Kiro Specs](https://kiro.dev/docs/specs/)，页面标注更新于 2026-11-12，访问于 2026-11-14。

对本项目的含义：

- 适合拆成 `product.md`、`architecture.md`、`security.md`、`coding-standards.md` 等稳定文档。
- 当前 M1 另建 `requirements.md`、`design.md`、`tasks.md`。
- 业务状态机、接口契约和评测用例应放到当前 Spec，而不是全部塞进全局架构文档。

### 5. GitHub Copilot：仓库级、路径级和 Agent 级指令分层

GitHub 官方文档支持仓库级 `.github/copilot-instructions.md`、按路径生效的 `NAME.instructions.md`，以及位于仓库不同目录的 `AGENTS.md`。当多个作用域同时生效时，距离当前工作目录更近的 Agent 指令优先。

来源：

- [Adding repository custom instructions for GitHub Copilot | GitHub Docs](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)，访问于 2026-11-14。

对本项目的含义：

- 根目录放全局硬约束。
- `backend/agent/`、`backend/refund/`、`apps/web/` 可分别增加局部规则。
- 退款、支付和权限相关目录应有更严格的专用说明和测试要求。

## 三、跨厂商共同趋势

以下内容是有官方资料交叉支持的共同模式，而不是某一家厂商的独有功能：

| 模式 | 含义 | 为什么重要 |
|---|---|---|
| 仓库化项目记忆 | 用 `AGENTS.md`、`CLAUDE.md`、Steering 或 Custom Instructions 保存项目知识 | 降低跨会话重复解释和上下文丢失 |
| 先规格后实现 | 先明确用户故事、范围、验收和技术设计，再生成任务 | 防止 Agent 自行补齐未定义需求 |
| 分层上下文 | 全局原则、局部规则、按需技能分开加载 | 避免一个超大文件污染所有任务 |
| 小步交付 | 围绕一个可验证闭环进行实现和审查 | 降低错误累积和 Review 成本 |
| 可运行检查 | 测试、构建、类型检查、Lint、截图和业务评测 | 给 Agent 一个真实的完成信号 |
| 确定性护栏 | hooks、权限、沙箱、CI、服务端校验 | 关键规则不能依赖模型记忆 |
| 独立审查 | 让未参与实现的上下文对照规格审查 | 降低实现者为自己的方案辩护的偏差 |
| 人审关键节点 | 规格、计划、任务与高风险操作保持人工确认 | AI 加速不等于放弃责任边界 |

## 四、厂商差异与适用条件

### OpenAI Codex

特点：以任务执行为中心，强调上下文、计划、`AGENTS.md`、测试/审查闭环、沙箱和批准策略。适合交互式工程任务，也支持通过计划和子任务管理复杂工作。

### Anthropic Claude Code

特点：强调先通过访谈形成 `SPEC.md`，把可执行检查交给 Agent，并用 hooks、权限和沙箱使不可违反的规则确定化。适合复杂代码库和需要严格命令执行边界的团队。

### GitHub Spec Kit

特点：把规格驱动开发流程产品化和模板化，强调 Constitution、规格、计划、任务、实现、收敛。适合需要跨团队标准化流程、留存交付证据的项目。

### AWS Kiro

特点：把长期项目 Steering 与功能 Specs 明确分开，并以 `requirements.md`、`design.md`、`tasks.md` 作为结构化交付物。适合希望将产品意图、技术约束和任务执行都文档化的团队。

这些方案并不互斥。较稳妥的组合是：

```text
OpenAI/Anthropic 式可执行检查
        +
GitHub Spec Kit 式规格到任务流水线
        +
Kiro 式 Steering 与当前 Spec 分层
```

## 五、推荐的从零启动流程

### 第 0 步：保存原始设计，不覆盖它

将现有分析报告原样归档为评审记录，例如：

```text
docs/reviews/2026-11-14-initial-architecture-review.md
```

它回答“为什么形成这些判断”，是后续设计变更的历史证据。

### 第 1 步：建立项目 Constitution

这是写代码前最重要的第一步。内容控制在一页到数页，至少包含：

- 产品目标和非目标。
- 目标用户与首批核心场景。
- 架构原则，例如单主 Agent + Tool + Workflow。
- 安全边界，例如服务端授权、人工审批和高风险操作。
- 完成定义，例如测试、评测、Trace 和业务验收。
- 文档权威顺序和变更方式。

它不是完整需求规格，也不应该复制整份评审报告。它约束后续所有功能和 AI 编码行为。

### 第 2 步：建立长期上下文索引

建议最小文件集合：

```text
AGENTS.md
docs/
  product/
    charter.md
    non-goals.md
  architecture/
    overview.md
    invariants.md
  adr/
    0001-single-agent-with-tools-and-workflows.md
  specs/
    M1-order-refund/
      requirements.md
      design.md
      tasks.md
      acceptance.md
  evaluations/
    M1-cases.md
  CURRENT.md
```

`AGENTS.md` 只声明：

- 项目文档的阅读顺序。
- 当前里程碑在哪里。
- 如何安装、运行、测试和评测。
- 不可违反的约束。
- 什么情况必须停止并请求人工决策。
- 完成证据必须包含什么。

### 第 3 步：编写第一个可交付 Spec

第一版选择“订单查询 + 取消/退款申请”纵向切片。规格至少包含：

- 用户故事和不进入本期的能力。
- 订单、申请、受理、处理中、成功、失败、人工处理的业务状态机。
- 查询、资格校验、确认、提交、查询结果和人工接管的 API/Tool 契约。
- 多租户、身份、数据权限和幂等要求。
- 超时、重复提交、部分成功和恢复行为。
- 可执行的验收用例与评测指标。

### 第 4 步：从 Spec 生成任务，而不是直接“做一个客服系统”

任务必须能对应到验收条件，例如：

- 实现订单查询 Tool 和契约测试。
- 实现退款资格规则及反例测试。
- 实现 Workflow 持久状态和恢复。
- 实现幂等提交与重复请求测试。
- 实现 Trace 和审计记录。
- 实现越权访问拦截及安全测试。

### 第 5 步：实现、检查、审查、收敛

每个任务按以下闭环完成：

```text
实现
  → 运行测试/类型检查/构建
  → 运行业务评测或模拟场景
  → 对照 Spec 独立审查
  → 修复不一致
  → 更新 CURRENT.md 和必要 ADR
```

## 六、如何防止大型项目跑偏

### 1. 明确文档权威顺序

建议固定为：

1. 产品宪章和不可突破的安全/架构约束。
2. 已批准 ADR。
3. 当前里程碑 Spec 和验收用例。
4. 任务与代码。

冲突时上层优先。修改上层文档必须给出原因；不能因为 Agent 实现更方便就静默修改目标。

### 2. 原始评审与活文档分开

- 原始评审记录不变，保留当时证据。
- 活架构文档随着批准决策演进。
- 每个关键变化使用 ADR 记录“上下文、选择、后果”。

### 3. 每个任务都绑定验收 ID

例如：

```text
Task T-04 → Acceptance AC-03、AC-05
```

没有对应验收条件的任务，不应直接进入实现；可能说明范围尚未澄清。

### 4. 用确定性机制守住不可例外的规则

对本项目尤其包括：

- Agent 不能绕过 Tool 直接访问业务数据库。
- 权限校验必须在服务端和 Tool 执行层完成。
- 高风险业务提交必须使用幂等键。
- 业务状态变更必须经过 Workflow。
- 生产配置、密钥和跨租户数据不能由模型自主处理。
- 合并前必须通过约定测试和安全检查。

### 5. 控制全局上下文体积

全局文档重要，不代表每次都应全文进入模型上下文。应通过索引和分层加载让 Agent 只读取与当前任务有关的规格、ADR 和代码规则。全局文档的职责是保留决策和约束，当前 Spec 的职责是指导实现。

## 七、对本项目的直接建议

现有电商客服分析报告值得长期保留。建议不要重写或抛弃它，而是进行两层转换：

- 把“项目定位、总体架构、七层边界、核心风险、阶段路线”提炼为 `docs/architecture/overview.md`。
- 把“M1 订单与退款闭环”派生为 `docs/specs/M1-order-refund/` 下的需求、设计、任务和验收文档。

下一步工作的准确描述不是“直接开始编码”，也不是“继续写一份更大的全局文档”，而是：

> 将现有全局评审固化为项目基线，再从中派生第一个可执行规格，并让代码、测试、评测和审查都绑定到该规格。

这样才能同时保住全局视角和开发执行效率。

## 八、来源汇总

1. OpenAI, [Best practices](https://learn.chatgpt.com/guides/best-practices)，访问于 2026-11-14。
2. OpenAI, [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)，访问于 2026-11-14。
3. Anthropic, [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices)，访问于 2026-11-14。
4. GitHub, [Spec Kit](https://github.com/github/spec-kit)，访问于 2026-11-14。
5. GitHub Docs, [Adding repository custom instructions for GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions)，访问于 2026-11-14。
6. AWS Kiro, [Steering](https://kiro.dev/docs/steering/)，访问于 2026-11-14。
7. AWS Kiro, [Specs](https://kiro.dev/docs/specs/)，页面标注更新于 2026-11-12，访问于 2026-11-14。
