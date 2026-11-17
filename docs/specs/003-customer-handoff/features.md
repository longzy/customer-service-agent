# 客户转人工闭环 features：转接闭环

- 状态：草案
- 日期：2026-11-17
- 说明：Plan 通过后细化；Build 阶段一次做一个 feature 并更新 `passes`。
- 原则：垂直票；每张票有 demo path；blocking edges 29→30→31。

| ID | 内容 | AC | Demo path | passes | Blocked by |
|---|---|---|---|---|---|
| T-29 | 客户登录 + 聊天 + AI + 转人工 | AC-30、AC-31、AC-32 | 客户登录→聊天→发“转人工”→看到排队 | false | — |
| T-30 | 坐席登录 + 队列 + 领取 + 接管 | AC-34、AC-35、AC-36 | 坐席登录→领取→接管→客户看到“人工已接入” | false | T-29 |
| T-31 | 回复 + 关闭/转回 + 客户甲/乙端到端 + 审计/限速 | AC-33、AC-37、AC-38、AC-39 | 客户甲/乙完整走通；审计/限速收口 | false | T-30 |

- 每张票穿过 DB/API/UI/tests；安全/审计/限速折进票内。
- Build 前不编码；执行卡写在 `docs/tasks/003-customer-handoff/`。
