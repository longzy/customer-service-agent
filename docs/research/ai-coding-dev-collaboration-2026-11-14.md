# 规格驱动开发与人类审核门禁：2025–2026 一手资料调研

- 调研日期：2026-11-14
- 适用项目：企业级电商智能客服 Agent（M1 订单查询与未发货订单取消）
- 调研问题：只有 `docs/specs` 目录里的规格就开工，系统是否真的可确定？规格与实现之间的歧义空隙出现在哪里，用什么机制补救？
- 调研方法：只采信官方文档、官方仓库和官方规范原文，逐页打开核对后引用。本文所有规格驱动与实践结论均能在官方页面找到出处，因此没有引入第三方博客或媒体作为论据。
- 证据边界：本文区分标记为【事实】（一手来源原文可核对）与【推断】（我的判断，可被反驳）。厂商文档能证明"主流工具把哪些环节做成了显式门禁"，不能证明这些门禁在本项目就能消除错误。

- 历史说明：本文写于 2026-11-14，文件名与状态字段是当时约定；当前文档模型见 [WORKFLOW](../process/WORKFLOW.md)（`requirements/design/tasks` + `STATUS`）。

## 一、核心结论

1. **规格文档是必要但不充分的。** 官方工具链自己就把"规格之外还要加质量门"写进了流程：GitHub Spec Kit 的短路径只有 specify → plan → tasks → implement → converge，而 clarify / checklist / analyze 被定义为"有实质歧义时才加"的可选质量门。换言之，规格写完不等于歧义已消除，歧义消除是独立的一道工序。
2. **歧义空隙主要出现在四个位置，而不是"文档写少了"。** 一是规格内部不可测的措辞；二是规格之间的逻辑冲突（需求↔设计↔任务）；三是规格没写、模型自动用"看似合理的假设"补全的地方；四是模型自认为"看起来做完了"的执行层。前两类靠评审与一致性检查，第三类只能靠在规格里显式标注未知，第四类只能靠外部的 pass/fail 检查与人工签字。
3. **"必须"写在文档里不构成保证。** Anthropic 明确把指令分成非确定性（提示词、`CLAUDE.md`、技能）与确定性（hooks、权限规则、CI、分支保护）两类；只有后者"无论模型怎么决定都会执行"。本仓库当前所有"必须"都还是第一类。
4. **可控的人机协作由七道门禁组成，且每道有唯一责任人。** 澄清（问题写回规格）→ 需求质量评审（检查清单由评审者勾，不能由实现者自勾）→ 规格一致性检查（只读、跨文档）→ 计划/设计评审（只读、显式批准）→ 任务分解评审（任务必须能反查到需求）→ 验收与回归（可执行、可追溯、变更后全量重跑）→ 合并（人决定）。业界工具的差异只在门禁形态，不在是否要门禁。
5. **规格是"廉价的代理"，但代理的保真度取决于评审者。** sspec 项目把这一点讲得最直白：验证要前移到规格，因为判断代码正确性是最后发生、最难撤销的高成本操作；它同时承认，若开发者无法判断代码质量，这套方法不适用。这正好回答了"会不会是在让 AI 猜需求"：**规格本身不防猜，能否防猜取决于有没有人能对规格做出真实的判断。**

## 二、证据

### 1. 规格之外必须有质量门（对应结论 1）

【事实】Spec Kit 文档把两种路径分开：较小功能走 specify → plan → tasks → implement → converge；生产级功能才插入 clarify、checklist、analyze 三道门。命令参考页写得更直接：命令"设计为按顺序运行，但只有 `/speckit.specify` 在 `/speckit.plan` 之前是严格必需的"，而 clarify、checklist、analyze 是"对任何有实质歧义的工作才加的质量门"。

- [Spec-Driven Development Quickstart | Spec Kit](https://github.github.io/spec-kit/quickstart.html)
- [Agentic SDD | Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)

【事实】三道门各自对应的正是歧义的不同来源：

| 门 | 官方定位 | 解决的歧义类型 |
|---|---|---|
| `/speckit.clarify` | 就规格中未充分说明处提**最多五个**针对性问题，把答案写回 `spec.md`；"避免你在歧义之上做设计" | 规格没写清的部分，且答案必须落到文件而不是聊天 |
| `/speckit.checklist` | "给你的需求写的单元测试"，检查规格是否完整、清晰、无歧义、一致；**由评审者拥有**，实现不得静默自我批准；`/speckit.implement` 会把未勾选项当作门禁并先询问 | 规格自身质量 |
| `/speckit.analyze` | **只读**，跨 `spec.md`、`plan.md`、`tasks.md` 报告冲突、缺口与歧义（例如"没有对应需求的任务"、"与规格矛盾的计划选择"）；发现后回源修改再重跑直到干净 | 规格之间的不一致 |

来源同上 ([Agentic SDD](https://github.github.io/spec-kit/reference/agentic-sdd.html))。

【事实】即便如此，官方方法论仍承认规格不可能在开工前完备：代码生成"只要规格与实施计划足够稳定就可以开始，但它们不必是'完整'的"；剩下的部分靠 converge 循环收敛，而 converge 是**追加式**的——只允许往 `tasks.md` 追加缺口任务，不改代码、不删内容。

- [Specification-Driven Development（方法论文原稿）](https://github.com/github/spec-kit/blob/main/spec-driven.md)
- [Agentic SDD | Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)

【推断】所以"规格已批准 → 可以确定地实现"这个推理链缺了一环：批准的是**当时可判断的部分**，未判断的部分仍在，只是被隐藏。让它可见，需要在批准前主动做一次"未知清点"，而不是指望实现阶段自然暴露。

### 2. 歧义空隙的具体位置（对应结论 2）

#### 2.1 规格内部：不可测的措辞

【事实】Kiro 的 Analyze Requirements 列出它专门捕获的五类问题，其中"Ambiguities"的定义是：像 "large files" 或 "fast response times" 这样的表述，"会产生彼此背离的实现"。其余四类是：需求之间的逻辑不一致（各自成立、合起来不可能）、约束冲突、未声明的假设（引用了未定义的概念或行为）、缺失的边界情况（失败模式、边界条件、并发访问）。

- [Analyze Requirements | Kiro](https://kiro.dev/docs/specs/analyze-requirements/)

【事实】Kiro 要求需求用 EARS 句式 `WHEN [条件/事件] THE SYSTEM SHALL [预期行为]`，官方给出的收益是清晰、可测试、可追溯、完整性——"每条需求都能直接转成测试用例"。

- [Feature Specs | Kiro](https://kiro.dev/docs/specs/feature-specs/)

【推断】本项目 `requirements.md` 的 FR 条目多数是"必须……"式陈述，部分带前置条件（如 FR-07"写接口超时后必须使用原幂等键查询状态"），但句式不统一，也未必写出可观测结果。这类句子对人可读，对"能否直接转成测试"不够稳定：它是"意图"，不是"用例"。

#### 2.2 规格之间：需求↔设计↔任务的漂移

【事实】Spec Kit 把这类检查做成独立只读命令，理由是"在实现之前、工件还便宜的时候"修；`/speckit.analyze` 的典型发现就是"没有对应需求的任务"和"与规格矛盾的计划"。Kiro 在需求迭代后要求手动 **Sync Files**，让 `tasks.md` 映射到新需求；这说明需求变化后任务不会自动跟随。

- [Agentic SDD | Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)
- [Best practices | Kiro](https://kiro.dev/docs/specs/best-practices/)

【事实】Spec Kit 维护者按自己的 SDD 流程做 bundler 功能时，**第一遍实现后仍需一次 converge 追加遗漏任务**；官方把这当成"检查实现对照意图、而不是把第一遍当完成"的正面案例。

- [How Spec Kit Develops Spec Kit | Spec Kit](https://github.github.io/spec-kit/guides/agentic-sdlc.html)

#### 2.3 规格没写：模型默认会补全

【事实】Spec Kit 的方法论把"不要猜"写成模板级的强制约束：创建规格时"标记所有歧义：使用 `[NEEDS CLARIFICATION: 具体问题]`"，并且"**不要猜**：如果提示没有说明，就标记它"。原文举的例子是：不要让模型自行假设"登录系统"就是邮箱密码认证，而要标记"认证方式未指定"。

- [spec-driven.md](https://github.com/github/spec-kit/blob/main/spec-driven.md)

【推断】这条约束的存在本身就是证据：**模型的默认行为是做出看似合理的假设并继续**。因此"规格写全了所以不会猜"不成立；只有当规格里出现可被检查的未知标记，且这些标记被清零或显式接受，才算消歧。附带风险：`[NEEDS CLARIFICATION]` 若无人清零就会烂在文档里，checklist 的"不存在遗留标记"检查项正是为此设计。

#### 2.4 执行层：模型判断不是确定性执行

【事实】Anthropic 把每条指令归为两类：非确定性（提示词、`CLAUDE.md`、技能——模型"通常"遵守，但**没有保证**）与确定性（hook、deny 规则、托管设置、CI——由 harness 每次强制执行）。同一张表里，"何时算完成"的非确定性形式是"请求证据 / `/goal` / `/code-review`"，确定性形式是"测试、类型检查、Stop hook、CI"；"谁有最终决定权"的非确定性形式是"Claude 自己总结做了什么"，确定性形式是"分支保护、批准合并的人"。

- [Best practices for Claude Code | Anthropic](https://code.claude.com/docs/en/best-practices)

【事实】同一页明确指出失败根因：模型"没有可跑的东西来判断工作是否真的完成"时，只能按"看起来完成了"收工；因此要给一个返回 pass/fail 的检查，并要求提供命令与输出作为证据。

【事实】Spec Kit 在自己的 SDLC 说明里也划线：agent 在 GitHub Actions 上运行"并不使它的推理成为确定性脚本"；确定性测试与发布仍由普通 Actions 执行，是否推进、是否合并由维护者决定。

- [How Spec Kit Develops Spec Kit | Spec Kit](https://github.github.io/spec-kit/guides/agentic-sdlc.html)

【事实】两家工具的"去掉门禁"都是显式选项而非默认：Kiro 的 Quick Spec 一次性跑完三段，明说是"**without approval gates**"，适用于充分理解且信任输出的功能；Gemini CLI 在非交互模式下自动批准进入/退出 Plan Mode，并在退出时切到 YOLO 模式。

- [Feature Specs | Kiro](https://kiro.dev/docs/specs/feature-specs/)
- [Plan Mode | Gemini CLI](https://geminicli.com/docs/cli/plan-mode/)

### 3. "必须"必须落在 harness，而不是文档（对应结论 3）

【事实】Anthropic 的判决规则很简单：如果某条规则"每次都必须发生（或永不发生）"，就把它从 `CLAUDE.md` 移进 hook、deny 规则或托管设置；"从那以后，结果不再取决于模型记得什么或决定了什么"。并且给了一个可操作的信号：**如果你不断给某条 `CLAUDE.md` 加粗体还是被忽略，说明它属于 hook。**

- [Best practices for Claude Code | Anthropic](https://code.claude.com/docs/en/best-practices)

【事实】Gemini CLI 的 Plan Mode 也用同样的思路把"计划阶段不许改代码"做成策略而非提示：该模式只允许读文件、检索、问用户和研究型子代理，写操作仅限计划目录下的 `.md`；且**在其他模式下授予的工具批准不会延续到 Plan Mode**。

- [Plan Mode | Gemini CLI](https://geminicli.com/docs/cli/plan-mode/)

【推断】对本项目，"服务端授权""幂等""不越权"目前写在 `docs/architecture/invariants.md` 与 `requirements.md` 里，属于非确定性层。它们真正生效要等 CI、Tool Gateway 与测试落地；在此之前把它们当成"已保证"是过度自信。

### 4. 人类门禁的形态与责任人（对应结论 4）

【事实】**澄清是显式停顿。** Gemini CLI 的 Plan Mode 描述了一个可照抄的节奏：先研究并与用户讨论方案，**"Gemini CLI 会停下来等待你的确认"**，然后才起草正式计划；计划写成 Markdown 文件，可用 `Ctrl+X` 在编辑器里直接改步骤、写行内批注（例如"等等，这里是不是该复用已有的 `Logger` 类？"），保存后 CLI 自动读取改动并重新出计划，再交给用户正式批准。

- [Plan Mode | Gemini CLI](https://geminicli.com/docs/cli/plan-mode/)

【事实】**需求评审的产物是"有主的检查清单"，不是一次会议。** Spec Kit 明确：自定义 checklist 是"评审者拥有的需求质量审查工件"；agent 只有被明确要求时才能协助评估，"实现不得静默自我批准"；`[x]` 表示评审者认定该质量准则已满足，**不表示实现完成**。

- [Agentic SDD | Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)

【事实】**实施计划评审发生在技术栈进入的时候。** Spec Kit 规定"要做什么/为什么"属于 specify，"技术栈、架构与实现细节"属于 plan；Kiro 因此提供两条变体流程（Requirements-First / Design-First）并在开始时就要选定。

- [Agentic SDD | Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)
- [Feature Specs | Kiro](https://kiro.dev/docs/specs/feature-specs/)

【事实】**独立评审者要用干净上下文。** Anthropic 建议让一个从未见过本次对话的评审者按 `SPEC.md` 审 diff，并强调"评审者只报影响正确性的缺口、跳过风格"——因为被要求找问题的评审者"总能找到点什么"，逐条修完会得到多余的抽象层和不可能发生的测试。同页还给出只读工具限制的子代理配置（`tools: Read, Grep, Glob`），这个限制由 harness 执行而非提示。

- [Best practices for Claude Code | Anthropic](https://code.claude.com/docs/en/best-practices)

【事实】**验收与回归要么可执行，要么不存在。** Kiro 的 Correctness 功能提出一个直白的问题："当 AI 生成代码时，你怎么知道它符合你的意图？"它的方法是把 EARS 需求转成属性（property）做属性测试，自动生成成百上千输入；同时明确给出局限：**只提供证据，不是证明**；属性写得太弱或写错，测试会通过而真实行为仍然错；不是所有需求都能映射成属性。对于"不允许变化的行为"，Bugfix Spec 的写法是 `WHEN … THEN the system SHALL CONTINUE TO …`，并用属性测试覆盖回归。

- [Correctness | Kiro](https://kiro.dev/docs/specs/correctness/)
- [Best practices | Kiro](https://kiro.dev/docs/specs/best-practices/)

【推断】这套分工的共同点：AI 负责"生成候选"和"跑检查"，人负责"定义什么是正确"和"签字"。把定义权交给模型，门禁就退化成模型自评。

### 5. 为什么规格能当前置代理，以及它的前提（对应结论 5）

【事实】sspec 项目的自我定位："AI 编码 agent 能廉价、大量地生成代码，但判断代码是否正确是最昂贵的操作——它最后发生，且难以撤销。"其核心策略是把验证从昂贵的最终产物前移到廉价且忠实的代理——规格："你可以从规格预测代码会长什么样，并在写代码之前做出判断。"生命周期里有两个硬停顿（design gate / implementation gate），agent **必须**等到审查通过才能继续。

- [sspec | PyPI](https://pypi.org/project/sspec/)（该项目自述，属于第一方但非大厂文档，按项目资料看待）

【事实】同一页面也写出了适用条件：适合"能判断代码是否正确、希望 agent 加速而不是替你做决定"的开发者，且愿意在写代码前投入时间对齐方向；"大概率不适合"那些"无法判断代码质量、需要 agent 承担全部责任"的人。

【推断】这是对"让 AI 猜需求"最准确的反面表述：不是规格不够多，而是**判断缺位**。规格把判断前移了，但如果没有人真的在规格上做判断，前移的只是形式——文档变长，未知仍在，只是从对话挪进了仓库。

## 三、与本仓库现状的差距

现状（截至 2026-11-14）：宪章、架构不变量、ADR-0001~0003、M1 四份规格与 19 条验收用例均已批准；`docs/process/README.md` 定义了文档权威顺序、任务闭环（定界→设计→实施→验证→审查→记录）和 `CURRENT.md` 字段；T-01 因 ADR-0004 与 `ui.md` 未确认而阻塞，说明"未确认不开工"实际生效过一次。

| # | 环节 | 业界机制 | 本仓库现状 | 影响 |
|---|---|---|---|---|
| G1 | 澄清 | clarify 提问写回规格；未定义项用 `[NEEDS CLARIFICATION]` 标记后再清零（[Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)、[spec-driven.md](https://github.com/github/spec-kit/blob/main/spec-driven.md)） | 待确认项散落在 `CURRENT.md` 与 `design.md` §10，分工清晰但无标记规范、无清零检查；M1 的 4 个阻塞问题靠评审逐个发现并决策 | 未发现的不确定项会在实现时被模型默默补全 |
| G2 | 需求质量评审 | EARS 句式 + 检查清单由评审者勾选（[Kiro](https://kiro.dev/docs/specs/feature-specs/)、[Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)） | 需求以"必须……"陈述为主，句式不统一，也未必写可观测结果；无需求质量检查清单 | 需求无法稳定转测试，验收用例与需求的对应靠人工解释 |
| G3 | 规格一致性 | 只读 analyze：任务必有对应需求、计划不矛盾（[Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)） | `关联：AC-xx` 是约定；T-01 的"关联：全部"曾不可判定（已修），T-13 仍写"全部" | 同类漂移可能再次出现且无人报警 |
| G4 | 计划/设计评审 | 计划只读起草、显式批准、可在文件上批注（[Gemini CLI](https://geminicli.com/docs/cli/plan-mode/)） | 里程碑级批准已存在；单任务级"§4.2 设计"只有完成标准，无人类确认门 | 小步实现时接口与失败路径由实现者自行定义 |
| G5 | 任务分解 | 按依赖排序、按用户故事分阶段、任务可反查需求 | `tasks.md` 已按 Phase 排序，T-01 已有产出清单与完成标准，并给出"不直接对应 AC、为全部 AC 提供基座"的豁免先例 | 基本对齐；该豁免只是先例，未写成规则，其他任务可自称基座绕开 AC |
| G6 | 独立评审 | 干净上下文、只读工具的评审者（[Anthropic](https://code.claude.com/docs/en/best-practices)） | §4.5 审查由实现者自己做 | 实现者会为自己已做的选择辩护 |
| G7 | 验收与回归 | AC→测试映射；属性测试覆盖"不得改变的行为"；converge 追加缺口直到无缺口（[Kiro](https://kiro.dev/docs/specs/correctness/)、[Spec Kit](https://github.github.io/spec-kit/reference/agentic-sdd.html)） | `acceptance.md` 已要求证据与 AC 映射，但无机器可检查形式，也无 converge 式缺口检查 | "全覆盖"只能靠人抽查 |
| G8 | 确定性执行 | 不可违反的规则放 hook / CI / 分支保护（[Anthropic](https://code.claude.com/docs/en/best-practices)、[Spec Kit SDLC](https://github.github.io/spec-kit/guides/agentic-sdlc.html)） | 仓库无 `.github/` 工作流，无 hook、无分支保护证据，全部规则仍是文档约定 | 关键约束的实际强度等于模型的配合度 |

## 四、可落地的流程建议

原则：**门禁加在有判断的地方，产出物能被人复核，判断权归具体角色。** 新增的东西尽量挂在现有环节上，不新建并行体系。

| 门禁 | 加在哪个环节 | 产出物 | 谁做判断 |
|---|---|---|---|
| M1 澄清 | 规格草案完成、批准之前（现状：`requirements.md`/`design.md` §10/`CURRENT.md` 待确认项） | `docs/specs/<M>/clarifications.md`：每条一个 ID、问题、选项、答案、影响的需求 ID；同时规定未决项必须留在文档中，禁止口头消解 | 业务/产品负责人答；技术负责人判断是否需要改 ADR |
| M2 需求质量评审 | 澄清（M1）之后、批准之前 | `docs/specs/<M>/review-checklist.md`：每条需求是否可观测、是否有边界与失败路径、状态↔对外表达是否一一对应、是否有遗留未决项。**勾选只能由评审者做，实现者不得自勾** | 需求评审者（非实现者） |
| M3 规格一致性 | 每份规格更新后（可先人工，骨架落地后进 CI） | 只读检查报告：每个任务至少有一个 AC ID 或"基座豁免"标注；每条 AC 至少被一个任务覆盖；术语只在基线术语表定义一次 | 评审者看报告，作者修源头 |
| M4 任务设计评审 | 每个任务的 §4.2 设计与编码之间（T-0x 开工前） | 任务设计卡：接口签名、状态迁移、失败路径、验证命令、绑定 AC ID；未确认则任务保持"未就绪" | 技术负责人；涉及权限/资金/状态机时加业务负责人 |
| M5 独立评审 | 实现完成、合并之前 | 差异 vs AC 的缺口报告（只报影响正确性的项，跳过风格）；评审者使用只读工具与干净上下文 | 独立评审者（不含实现者） |
| M6 验收与回归 | 每个任务完成时 + 任何 Prompt/模型/Tool 变更后 | 测试与评测用例名内嵌 AC ID；变更后跑全量场景；输出"已覆盖/未覆盖 AC"清单和 Trace 样例 | 验收负责人签字；CI 只负责执行与阻断 |
| M7 合并门禁 | 合并到 `main` 之前 | CI 必需检查（测试、类型检查、Lint、AC 映射检查）+ 分支保护 + 必填证据 | 合并者（人） |

配套三条硬规则（这几条只有做成确定性机制才有意义）：

1. **未知项清零才算批准。** 规格里存在未关闭的澄清条目时，规格状态不得从"等待评审"变成"已批准"；`CURRENT.md` 的"待确认决策"与规格内的未决项必须是同一份事实的两个视图，不能各写一半。
2. **实现者不得自证。** M2 的检查清单、M5 的评审结论、M6 的验收签字，都不能由写代码的同一上下文给出；对应 Anthropic 对"非确定性自评"的警告和 Spec Kit 对"实现不得静默自我批准"的规定。
3. **关键约束下沉到 harness。** 骨架建立后立刻把这三件事做成 CI 或网关：AC 引用完整性、`invariants.md` 中可测条目的自动化测试、Tool Gateway 的越权与未知字段拒绝测试。在此之前，不要在文档里新增"必须"，因为新增的只是非确定性声明。

不推荐的做法（均有一手依据）：

- 用更长更细的规格去消灭歧义。官方方法论本身承认规格不必完整，靠 clarify + converge 收敛（[spec-driven.md](https://github.com/github/spec-kit/blob/main/spec-driven.md)）。
- 让实现者勾选需求质量清单，或让同一个 agent 自评完成。这正是 Spec Kit 与 Anthropic 都明确排除的做法。
- 把技术栈写进需求文档。Spec Kit 把技术细节划归 plan 阶段，混写会让需求随技术变动而失效（[Agentic SDD](https://github.github.io/spec-kit/reference/agentic-sdd.html)）。
- 让评审者"全面审查"。只报正确性缺口、跳过风格，否则会产出无意义的重构（[Anthropic](https://code.claude.com/docs/en/best-practices)）。

## 五、我的推断与限制

- 【推断】"AI 猜需求"的高发点不是模型能力不足，而是**规格里没有可被判断的对象**：没有 WHEN 条件、没有可观测结果、没有未决标记。把这三样补上，猜的空间大幅收窄；但即便补齐，仍有残余歧义由实现阶段发现——业界做法是承认它、用 converge 与回归收敛，而不是假装事前已消灭。
- 【推断】本项目当前最大的风险不是"规格不够细"，而是"规格之后的确定性执行缺位"：G6/G7/G8 都还没有实际承载物，一旦开始写代码，这些缺口会在没有报警的情况下被顺利跨过。
- 【限制】Kiro、Spec Kit 都是自带流程的产品，其文档天然倾向于证明"流程必要"；本文只引用它们的**功能事实与官方规则**，不把"用了就确定"当作结论。
- 【限制】OpenAI Codex 的官方最佳实践页（`learn.chatgpt.com`、`developers.openai.com`）在本次环境中多次无法访问（连接失败 / 403），因此本文未就 Codex 作出新的断言；仓库内既有的 `ai-coding-new-project-practices-2026-11-14.md` 对 Codex 的引述未经本次复核，引用时应标注这一点。
- 【限制】Gemini CLI 文档页面顶部提示：自 2026-06-18 起，免费层与 Google One 用户已由 Antigravity CLI 替代。Plan Mode 的机制描述仍可作为 Google 一方的工作流证据，但产品可用性需另行确认。
- 【限制】属性测试（PBT）在本项目是否值得引入未做评估；对含外部服务与不确定性的路径，Kiro 自己也说明更适合用示例测试（[Correctness](https://kiro.dev/docs/specs/correctness/)）。

## 六、参考来源

1. GitHub, [Spec-Driven Development Quickstart](https://github.github.io/spec-kit/quickstart.html)，访问于 2026-11-14。
2. GitHub, [Agentic SDD（命令与质量门参考）](https://github.github.io/spec-kit/reference/agentic-sdd.html)，访问于 2026-11-14。
3. GitHub, [How Spec Kit Develops Spec Kit: An Agentic SDLC](https://github.github.io/spec-kit/guides/agentic-sdlc.html)，访问于 2026-11-14。
4. GitHub, [spec-driven.md（Spec-Driven Development 方法论文）](https://github.com/github/spec-kit/blob/main/spec-driven.md)，访问于 2026-11-14。
5. AWS Kiro, [Specs](https://kiro.dev/docs/specs/)，访问于 2026-11-14。
6. AWS Kiro, [Feature Specs（EARS、Requirements-First / Design-First、Quick Spec）](https://kiro.dev/docs/specs/feature-specs/)，访问于 2026-11-14。
7. AWS Kiro, [Analyze Requirements](https://kiro.dev/docs/specs/analyze-requirements/)，页面标注更新于 2026-09-02，访问于 2026-11-14。
8. AWS Kiro, [Correctness with Property-based tests](https://kiro.dev/docs/specs/correctness/)，访问于 2026-11-14。
9. AWS Kiro, [Specs Best practices（含 SHALL CONTINUE TO 回归写法）](https://kiro.dev/docs/specs/best-practices/)，访问于 2026-11-14。
10. Anthropic, [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices)，访问于 2026-11-14。
11. Google, [Gemini CLI Plan Mode](https://geminicli.com/docs/cli/plan-mode/)，访问于 2026-11-14。
12. sspec 项目, [sspec | PyPI（项目自述，规格作为廉价代理）](https://pypi.org/project/sspec/)，版本 2.8.1，访问于 2026-11-14。
