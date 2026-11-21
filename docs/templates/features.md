# <feature> features

> 结构依据：Anthropic《Effective harnesses for long-running agents》的 feature list：`id`、`category`、`description`、`steps`、`passes`、`evidence`；初始化全部 `passes: false`，一次只做一个，验证通过才改 `true`。
> 仓库门禁：`scripts/check-docs.py` 要求 `brief.md` 的每个 AC 在本表出现；`AC` 列是追溯字段，不属于 Anthropic schema。

- 状态：草案
- 日期：YYYY-MM-DD
- 依据：`brief.md`、`plan.md`
- 构建顺序：按表格从上到下；同一时间只允许一行从 `false` 改为 `true`。

| ID | Category | Description（端到端行为） | Steps（验证步骤） | AC | Passes | Evidence |
|---|---|---|---|---|---|---|
| F-XX | <functional/security/ui> | <一个可独立演示的端到端行为> | <命令 + 手工步骤 + 可观察结果> | AC-XX | false | — |
| F-YY | <functional/security/ui> | <一个可独立演示的端到端行为> | <命令 + 手工步骤 + 可观察结果> | AC-YY | false | — |

## 规则

- 一行 = 一个可独立演示的端到端行为，穿过 DB/API/UI/tests；只改一层的拆成任务卡，不占一行。
- `Steps` 必须可执行并给出可观察结果；没有命令/步骤的行退回重拆。
- `Passes` 初始 `false`；`Steps` 全绿且 `Evidence` 非空后才改 `true`。
- `Evidence` 写命令、测试名、截图/录像路径、commit 与结论；具体计数引用 `docs/CURRENT.md` 验证块，不手抄；不得手写“已验证”。截图/录像放 `evals/reports/<spec>/`（已 gitignore），不要只写 `/tmp`。
- 不得为了让测试通过而改 `Description` / `Steps` / `AC`；要改先改 `brief.md` / `plan.md` 并重新评审。
- 横切 AC（审计/限速/越权）挂到首次触达它的行，不单开“安全行”。
- `F-xx` 是行为编号；执行卡用 `F-xx`，一卡对应一行，见 `docs/templates/task-design-card.md`。
