# <feature> features

- 日期：
- 依据：`brief.md`、`plan.md`
- 规则：一次只做一个 feature；验证通过才把 `passes` 改为 `true`

| ID | 端到端行为 | 验证命令/步骤 | Demo path | passes | Blocked by |
|---|---|---|---|---|---|
| F-01 |  |  |  | false | — |
| F-02 |  |  |  | false | F-01 |

- 每条 feature 必须穿过 DB/API/UI/tests；只改一层的是任务，不是 feature。
- 没有验证命令或 demo path 的 feature，退回重拆。
- `passes` 只由测试/演示结果更新，不由计划完成更新。
