# 客户转人工闭环 features

> 结构依据：Anthropic feature list（`id`/`category`/`description`/`steps`/`passes`/`evidence`）；仓库门禁：`brief.md` 的每个 AC 至少一行。
> Steps 中的测试文件/命令在 Build 时创建；先写失败测试，再实现；`Evidence` 为空时不得把 `Passes` 改为 `true`。

- 状态：已批准
- 批准：2026-11-17（用户确认 14 条 feature 粒度）
- 日期：2026-11-17
- 依据：`brief.md`、`plan.md`
- 构建顺序：F-01 → F-02 → … → F-14；同一时间只允许一行从 `false` 改为 `true`。
- 切片映射：F-01~F-04 ≈ S-01；F-05~F-09 ≈ S-02；F-10~F-14 ≈ S-03。

| ID | Category | Description（端到端行为） | Steps（验证步骤） | AC | Passes | Evidence |
|---|---|---|---|---|---|---|
| F-01 | functional | 客户用种子账号登录，刷新/重新登录恢复到同一未关闭会话；登出或过期后 401；跨客户访问 404。 | 命令：`pytest tests/integration -k "AC_30"`；手工：`/login` 用 `customer_a` 登录→刷新 `/chat` 仍在同一会话→登出→再访问看到登录页；用 `customer_b` 登录后访问 `customer_a` 的会话 URL，看到 404。 | AC-30 | true | 2026-11-17：`./scripts/test-db.sh tests/integration/test_customer_auth_AC_30.py -q` → 13 passed；`./scripts/verify.sh --no-record` → pytest 481 passed、mypy 52 files；浏览器走查 customer_a 刷新仍在同一会话，登出后 `/chat` 回 `/login`，customer_b 打开该会话 URL 显示“会话不存在”。 |
| F-02 | functional | 客户发普通消息，10s 内收到 AI 回复；模型超时/不可用时自动转人工并看到排队。 | 命令：`pytest tests/integration -k "AC_31"`；手工：`customer_a` 发“你好”→看到 AI 回复；把 FakeModel 切成超时→再发→看到“排队中，请稍候”。 | AC-31 | true | 2026-11-17：`./scripts/test-db.sh tests/integration/test_customer_chat_AC_31.py -q` → 12 passed；`./scripts/verify.sh --no-record` → pytest 502 passed、mypy 54 files；浏览器正常回复与超时 QUEUED 均走查通过；幂等重试、长请求标识、24h 惰性关闭有专项用例。 |
| F-03 | functional | 客户发“转人工/人工客服/真人/找人工”，不调用模型即创建交接单并入队，客户看到排队；交接单含摘要/最近 20 条/AI 轨迹/原因/待办，`order_count=0`。 | 命令：`pytest tests/integration -k "AC_32"`；手工：`customer_a` 发“转人工”→看到“排队中”；测试断言交接单含摘要、最近 20 条、AI 轨迹、原因、待办、`order_count=0`。 | AC-32 | true | 2026-11-17：`./scripts/test-db.sh tests/integration/test_customer_handoff_AC_32.py -q` → 16 passed；`./.venv/bin/python -m pytest tests/unit/test_handoffs.py -q` → 33 passed；`./scripts/verify.sh --no-record` → pytest 561 passed、mypy 56 files；4 个关键词及 5 个空白/标点/换行变体均 0 次模型调用，交接单含摘要（≤500）/最近 20 条（正文 ≤4000 字）/AI 轨迹/原因/待办/脱敏（含 +86/分隔符/全角）/`order_count=0`；浏览器 customer_a 发“转人工”看到 QUEUED + “排队中，请稍候”。 |
| F-04 | functional | 客户自然表达/模型低置信（<0.6）/问订单/超范围/模型失败时，同样创建交接单入队；AI 不编造订单信息。 | 命令：`pytest tests/integration -k "AC_32"`；手工：FakeModel 返回 `confidence=0.4`→发消息→看到排队；再问“我的订单到哪了”→看到排队且回复不含订单信息。 | AC-32 | true | 2026-11-17：`./scripts/test-db.sh tests/integration/test_customer_handoff_triggers_AC_32.py -q` → 9 passed；`./.venv/bin/python -m pytest tests/unit/test_handoff_triggers.py -q` → 34 passed；`./scripts/test-db.sh -k "AC_32 or AC_31 or AC_30" -q` → 117 passed；`./scripts/verify.sh --no-record` → pytest 604 passed、mypy 56 files；浏览器 customer_a 低置信 0.4、customer_b 问“我的订单到哪了”均显示 QUEUED/排队中且无 AI 回复，交接单 reason/trigger/`order_count=0` 见执行卡。 |
| F-05 | functional | 坐席用 `agent_1`/`agent_2` 登录，8h session；登出/过期 401，超限 429，非 agent 403；未领取/他人会话 404。 | 命令：`pytest tests/integration -k "AC_34"`；手工：`/login` 用 `agent_1` 登录→刷新 `/queue` 仍在；错误密码 5 次→429；非 agent 账号→403；用 `agent_1` 请求未领取的 `conversation_id`→404。 | AC-34 | true | 2026-11-17：`./scripts/test-db.sh tests/integration/test_workspace_auth_AC_34.py -q` → 14 passed；`./scripts/test-db.sh -q` → 619 passed；`pnpm -C apps/workspace test` → 6 passed；`./scripts/verify.sh --no-record` exit 0；浏览器走查 `agent_1` 登录→刷新 `/queue`→登出，`agent_2` 连续 5 次错误密码后第 6 次 429，`supervisor_x` 登录 403 且不签发 session，`customer_a` 转人工后 `agent_1` 读未领取会话 404；走查后 `make dev-reset ARGS=--yes` 恢复干净演示数据。 |
| F-06 | functional | 多个 QUEUED 时，工作台队列按 FIFO 展示，摘要含客户账号/等待秒数/原因/脱敏末条/订单数 0；领取前不返回完整消息。 | 命令：`pytest tests/integration -k "AC_35"`；手工：`customer_a`/`customer_b` 先后转人工→`agent_1` 打开 `/queue`，确认顺序和摘要字段；确认看不到完整消息。 | AC-35 | true | 2026-11-18：`./scripts/test-db.sh tests/integration/test_workspace_queue_AC_35.py -q` → 10 passed；`./scripts/test-db.sh -k "AC_35" -q` → 10 passed、619 deselected；`pnpm -C apps/workspace test` → 9 passed；`./scripts/check-api-types.sh` → 契约一致；`./scripts/verify.sh --no-record` → pytest 629 passed、mypy 63 files；浏览器走查客户甲/乙先后转人工，`agent_1` 的 `/queue` 按 FIFO 显示客户甲 47 秒、客户乙 2 秒，摘要含客户账号/等待/原因/脱敏末条/订单数 0，未领取详情 404；走查后 `make dev-reset ARGS=--yes`；提交 f56d1df、c49d035、2672ea2。 |
| F-07 | security | 两个坐席并发领取同一交接单，只有一个成功，另一个 409；跨租户/越权 404；不自动分配。 | 命令：`pytest tests/integration -k "AC_35"`；手工：两个浏览器同时点“领取”，一个进入会话，另一个看到 409 `CLAIM_CONFLICT`；刷新队列不再出现该单。 | AC-35 | true | 2026-11-18：./scripts/test-db.sh tests/integration/test_workspace_claim_AC_35.py -q → 9 passed；./scripts/test-db.sh -k "AC_35" -q → 19 passed、631 deselected；pnpm -C apps/workspace test → 17 passed；./scripts/check-api-types.sh → 契约一致；./scripts/verify.sh --no-record → pytest 650 passed、mypy 63 files；浏览器走查 agent_2 先抢单后 agent_1 看到 409 提示并刷新队列，领取另一单进入会话页显示“已领取，等待接管”，截图 evals/reports/001-customer-handoff/F-07/；提交 5dc9b54、6f96fd5；评审 docs/reviews/001-customer-handoff/F-07.md 通过。 |
| F-08 | functional | 坐席领取后接管，客户看到“人工已接入”；坐席看到客户账号、消息、AI 轨迹、交接单、待办。 | 命令：`pytest tests/integration -k "AC_36"`；手工：`agent_1` 队列领取 `customer_a`→点接管→客户页出现“人工已接入”；工作台看到上下文。 | AC-36 | true | 2026-11-18：./scripts/test-db.sh tests/integration/test_workspace_takeover_AC_36.py -q → 9 passed；-k "AC_35 or AC_36" → 28 passed；pnpm -C apps/workspace test → 22 passed、apps/chat test → 22 passed；./scripts/check-contracts.sh → 契约一致；make verify → pytest 661 passed、mypy 63 files；浏览器走查 agent_1 领取/接管、客户看到“正在接入人工/人工已接入”，截图 evals/reports/001-customer-handoff/F-08/；提交 e3dd837、9a9e8b5、14a7d9b；评审 docs/reviews/001-customer-handoff/F-08.md 通过。 |
| F-09 | security | 第二坐席查看/接管已被领取的会话：领取 409、查看/接管 404。 | 命令：`pytest tests/integration -k "AC_36"`；手工：`agent_2` 打开 `agent_1` 已领取的会话 URL→看到 404；点领取→看到 409 `CLAIM_CONFLICT`。 | AC-36 | true | 2026-11-18：tests/integration/test_workspace_second_agent_AC_36.py → 8 passed；-k "AC_36" → 17 passed、652 deselected、0 skipped；make verify → pytest 682 passed、mypy 63 files；独立双轴评审通过（C-1/C-2 已关闭）docs/reviews/001-customer-handoff/F-09.md；浏览器走查 agent_2 旧队列 409、会话 URL 404、agent_1 同 URL 200，截图 evals/reports/001-customer-handoff/F-09/；提交 670c975、a99880a、da163b8、353c78e、c0c052f。 |
| F-10 | functional | 坐席回复持久化，客户 3s 轮询可见；人工中客户发消息不再触发 AI，消息不丢。 | 命令：`pytest tests/integration -k "AC_37"`；手工：`agent_1` 回复“您好，我是坐席 1”→客户 3s 内看到；客户在人工中再发一条→工作台看到，AI 不回复。 | AC-37 | false | — |
| F-11 | functional | 客户可在任意未关闭状态关闭会话，交接单/队列同事务关闭；关闭后再发 409。 | 命令：`pytest tests/integration -k "AC_38"`；手工：`customer_a` 在排队/人工中/接管后分别点关闭→看到“会话已结束”；再发消息→看到“会话已结束”。 | AC-38 | false | — |
| F-12 | functional | 坐席可关闭或转回 AI；转回后同一会话 AI 恢复历史；再次转人工生成新交接单；同一会话不出现两张 open 单。 | 命令：`pytest tests/integration -k "AC_38"`；手工：`agent_1` 转回 AI→客户发消息得到 AI 回复且历史还在；再发“转人工”→工作台出现新交接单，旧单已关闭。 | AC-38 | false | — |
| F-13 | security | 登录/转人工/领取/接管/回复/关闭/转回有审计；审计不可改删；401/403/429 安全事件审计；登录/消息限速；审计失败变更 503。 | 命令：`pytest tests/integration -k "AC_39"`；手工：走一遍登录/转人工/领取/接管/回复/关闭/转回→查 `service_audit_events` 有记录；尝试改删审计→失败；注入审计失败→变更 503；连续登录/发消息触发 429。 | AC-39 | false | — |
| F-14 | security | 客户甲/乙都能完整走登录、聊天、转人工、被接管、回复、关闭、转回；甲读乙的会话/消息 404，各自交接单独立。 | 命令：`pytest tests/integration -k "AC_33"`；手工：两个浏览器分别登录 `customer_a`/`customer_b`，各自完整走一遍；用甲的 cookie 请求乙的 `conversation_id`，看到 404；工作台确认两张独立交接单。 | AC-33 | false | — |

## 规则

- 一行 = 一个可独立演示的端到端行为；只改一层的拆成任务卡，不占一行。
- `Steps` 必须可执行并给出可观察结果；没有命令/步骤的行退回重拆。
- `Passes` 初始 `false`；`Steps` 全绿且 `Evidence` 非空后才改 `true`。
- `Evidence` 写命令输出摘要、测试名、截图/录像路径、commit；不得手写“已验证”。
- 不得为了让测试通过而改 `Description`/`Steps`/`AC`；要改先改 `brief.md`/`plan.md` 并重新评审。
- 横切 AC（审计/限速/越权）已挂到首次触达它的行，不单开“安全行”。
- `F-xx` 是行为编号；执行卡用 `F-xx`，一卡对应一行，见 `docs/templates/task-design-card.md`。
