# 两轴评审提示词

- 状态：已批准
- 日期：2026-11-18
- 适用：T2/T3 feature 的独立上下文评审；与 [评审模板](../templates/review.md)、[评审 checklist](review-checklist.md) 配套
- 输入：`python3 scripts/review_pack.py F-XX` 生成的评审包；评审者仍须自己读 diff、代码与定向测试

## 0. 共同约束

- 两轴独立运行、互不共享结论：Standards 轴查规范，Spec 轴查规格符合度；不要合并或重新排序两轴发现。
- 评审者未参与实现；不要修改仓库文件。
- 门禁已由主评审跑过 `make verify-check`。评审者只跑分配给你的 `TEST_DB_NAME` 定向测试与独立探针；不运行 `make verify-check`/`make verify`，避免与主评审并行时争用测试库与 CPU。
- `test-db.sh` 默认每次运行使用一次性库（退出即删）；显式 `TEST_DB_NAME` 用于评审隔离，`TEST_DB_KEEP=1` 可保留现场。
- 先跑 `make review-check`（机械前置）；它失败时先修机械问题，不进入两轴深度评审。
- 每条发现标 **阻塞 / 建议 / 接受为后续**；判断性坏味道永远不是硬违规。
- 只报文档化标准的违反与判断性坏味道；工具已强制的不报（ruff/mypy/prettier/eslint、契约生成物、测试命名）。

## 1. Standards 轴

```text
你是独立上下文的 Standards 轴评审者，未参与实现。仓库：<repo>。
输入：评审包 <pack-path>。评审范围以包内固定点与 diff 为准。

读：AGENTS.md、CONTRIBUTING.md、docs/process/standards.md、docs/process/frontend.md、
docs/architecture/invariants.md、docs/architecture/overview.md、docs/process/review-checklist.md。

检查：
1. 模块边界与事务提交归属（api 只编排；conversations/identity 不越界）。
2. 身份只来自认证上下文、租户/本人过滤、越权 404、日志与 DTO 不泄露 PII。
3. 测试：_AC_XX 命名、独立测试库、无静默 skip、反向验证是否真实执行。
4. 前端（涉及 apps/）：组件目录/命名、生成类型未手改、无新颜色字面量、加载/空/错三态、
   a11y、测试未被弱化。
5. Fowler 坏味道只作 judgement call：Duplicated Code、Feature Envy、Primitive Obsession、
   Repeated Switches、Shotgun Surgery、Divergent Change、Speculative Generality、
   Message Chains、Middle Man、Refused Bequest、Mysterious Name、Data Clumps。

输出（中文，≤700 字）：实跑命令与结果；findings（文件:行号 + 规则/坏味道 + 理由，
分硬违规/判断）；一条结论：通过 / 有条件通过 / 不通过。
```

## 2. Spec 轴

```text
你是独立上下文的 Spec 轴评审者，未参与实现。仓库：<repo>。
输入：评审包 <pack-path>，其中含 AC 原文、features 行、执行卡 §1/§2 与 plan 全文。

检查：
1. AC 要求但缺失/部分实现的点（引 brief.md 原文行）。
2. 规格未要求但 diff 做了的事（新接口/字段/行为/配置）；区分 scope creep 与已批准到后续 feature。
3. 看起来实现但方式不符的点：状态机、错误码、权限/租户、事务、用户文案、
   读模型字段来源/缺省/截断。
4. 逐 AC 判定点给可复查证据：测试名 / 命令 / 文件行号；区分「F-XX 缺失」与
   「已批准到 F-YY 的后续承接」。
5. 证据一致性：执行卡 §4、features 的 Passes/Evidence、CURRENT 三处是否自洽。

输出（中文，≤700 字）：findings（引 spec 文件:行号 + 实现位置 + 标签）；
逐 AC 表格；一条结论：通过 / 有条件通过 / 不通过。
```

## 3. 聚合

- 主评审把两轴报告原样放入 [评审模板](../templates/review.md) 的 `## Standards 轴报告` 与 `## Spec 轴报告`，不合并、不重排。
- 结论只取：通过 / 有条件通过 / 不通过；阻断项必须写位置与修复项。
- 评审记录落 `docs/reviews/<spec>/F-XX.md`，并在执行卡 §5 引用。
