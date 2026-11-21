# 订单查询 features

> 结构依据：Anthropic feature list（`id`/`category`/`description`/`steps`/`passes`/`evidence`）；仓库门禁：`brief.md` 的每个 AC 至少一行。
> Steps 中的测试文件与命令在 Build 时创建；先写失败测试，再实现；`Evidence` 为空时不得把 `Passes` 改为 `true`。
> 状态：草案（随 `brief.md`/`plan.md` 一起评审；plan 批准后细化 Steps，不跳过 G1/G2）。

- 状态：已批准
- 批准：2026-11-20（用户确认 F-25~F-29 粒度与构建顺序）
- 日期：2026-11-20
- 依据：`brief.md`、`plan.md`
- 构建顺序：F-25 → F-26 → F-27 → F-28 → F-29；同一时间只允许一行从 `false` 改为 `true`。
- 切片映射：F-25 ≈ S-01；F-26~F-27 ≈ S-02；F-28 ≈ S-03；F-29 ≈ S-04。

| ID | Category | Description（端到端行为） | Steps（验证步骤） | AC | Passes | Evidence |
|---|---|---|---|---|---|---|
| F-25 | functional | 客户账号与 OMS 客户身份绑定；订单查询经授权网关执行，只返回本人同租户订单；未绑定/他人/不存在统一"查无此单"。 | 命令：`./scripts/test-db.sh tests/integration/test_order_query_AC_51.py -q`（含 `AC_51` 归属用例）；手工：种子后 `customer_a` 查 `ORD-10001` 成功、`customer_b` 查同一单看到"查无此单"；把 `customer_a` 的 `oms_customer_id` 置空再查仍"查无此单"且聊天不报错；`./scripts/test-db.sh tests/integration/test_migrations.py -q` 验证 0013 升级/回滚。 | AC-51 | true | 2026-11-20：`./scripts/test-db.sh tests/integration/test_migrations.py tests/integration/test_order_query_AC_51.py -q` → 8 passed（本人订单摘要、他人/不存在不可区分、未绑定不调用 OMS、普通消息、同键重放、带订单号的取消仍转人工、OMS 超时、0013 升级回滚）；`pytest tests/unit/test_order_queries.py -q` → 24 passed；全量 `make verify-check` → pytest 737 passed、mypy 70 files、31 条 AC；反向验证 2 组（归属置空 3 failed/4 passed；放开闸门+去早退 1 failed/6 passed）；dev 库真实 HTTP 双身份走查通过；两轴独立评审记录见 `docs/reviews/003-order-query/F-25.md`（Standards 通过；Spec C1~C3 已整改，最终结论以评审记录为准）；提交 ab5c1fd 与收口提交。 |
| F-26 | functional | 客户问"我的订单"列出最近 ≤5 单（快捷表达确定性查询，不依赖模型）；带订单号查单笔；多单/半截列最近订单候选让客户点选；闲聊不查；回复只含 OMS 摘要字段，消息带订单快照。 | 命令：`AC_50`/`AC_51`/`AC_52`/`AC_54` 集成用例；手工：`customer_a` 发"我的订单"看到最近订单列表（卡片由 F-29 承接）；发 `ORD-10001` 看到状态/商品/金额/时间；发两个订单号或半截订单号看到候选列表；发"订单"闲聊不触发查询也不建单；断言消息 `payload.orders` 与夹具一致且无 `items`/手机号。 | AC-50、AC-51、AC-52、AC-54 | true | 2026-11-21：`./scripts/test-db.sh tests/integration/test_order_query_AC_50.py tests/integration/test_order_query_AC_52.py tests/integration/test_order_query_AC_54.py tests/integration/test_order_query_AC_51.py tests/integration/test_customer_handoff_triggers_AC_32.py -q` → 30 passed；单测 `tests/unit/test_order_queries.py` 55 passed、`test_handoff_triggers.py` 39 passed；001 AC-31/32 文本与旧断言已同步；两轴评审首轮各 1 阻断已整改关闭并复核通过；用户追加“多单/半截列候选、快捷入口确定性”后再次全量验证；反向验证 8 组（澄清关闭 4 failed、模型意图关闭 3 failed、未绑定早退移除 1 failed、超范围前置移除 3 failed、回复护栏恢复 2 failed、事实词护栏关闭 4 failed、确定性入口关闭 1 failed、候选查询关闭 6 failed）；全量 `make verify` → pytest 794 passed、mypy 70 files、31 条 AC；评审记录见 `docs/reviews/003-order-query/F-26.md`。 |
| F-27 | functional | OMS 超时/异常/非法响应时提示重试且不建单；同会话连续两次订单失败转人工并说明原因；失败不并入模型失败计数。 | 命令：`./scripts/test-db.sh tests/integration/test_order_query_AC_53.py -q`；手工：`/_admin/faults` 注入 `get_order` 超时→客户看到"订单查询暂时不可用…"且队列无新单；再注入一次→客户看到"已转接人工"、队列出现交接单且 `trigger=order_query_failure`；注入非法响应→同一路径。 | AC-53 | false | — |
| F-28 | functional | 客户转人工时交接单带最近订单摘要与 `order_count`；工作台详情返回订单区；无订单为 0 且无空摘要；第二坐席仍 404。 | 命令：`./scripts/test-db.sh tests/integration/test_order_query_AC_55.py tests/integration/test_order_query_AC_56.py -q`；手工：`customer_a` 问单后说"转人工"→`agent_1` 队列/详情看到订单摘要与订单数；`customer_b` 无订单转人工→详情订单数 0；`agent_2` 访问该会话 404；构造订单查询成功后再手动转人工，断言复用最近快照。 | AC-55、AC-56 | false | — |
| F-29 | ui | 客户聊天订单卡片、工作台订单区、ui-spec 增补；审计 `order.queried`、Tool Trace、评测场景与 001 AC-31/32 测试同步。 | 命令：`pnpm -C apps/chat test -t "OrderCard"`；`pnpm -C apps/workspace test -t "Orders"`；`./scripts/test-db.sh tests/integration/test_order_query_AC_57.py -q`；`./scripts/eval.sh`；手工：375/900/1200/1440 截图无溢出、键盘可达；`sql` 查 `service_audit_events` 与 `tool_executions` 有 `order.queried` 与工具记录；修订 001 `AC-31`/`AC-32` 断言后全量 `make verify-check`。 | AC-57、AC-58 | false | — |

## 规则

- 一行 = 一个可独立演示的端到端行为；只改一层的拆成任务卡，不占一行。
- `Steps` 必须可执行并给出可观察结果；没有命令/步骤的行退回重拆。
- `Passes` 初始 `false`；`Steps` 全绿且 `Evidence` 非空后才改 `true`。
- `Evidence` 写命令输出摘要、测试名、截图/录像路径、commit；不得手写"已验证"。截图放 `evals/reports/003-order-query/`。
