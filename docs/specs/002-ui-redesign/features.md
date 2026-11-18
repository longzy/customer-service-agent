# UI 改版 features

> 结构依据：Anthropic feature list（`id`/`category`/`description`/`steps`/`passes`/`evidence`）；仓库门禁：`brief.md` 的每个 AC 至少一行。
> Steps 中的测试文件与命令在 Build 时创建；先写失败测试，再实现；`Evidence` 为空时不得把 `Passes` 改为 `true`。

- 状态：已批准
- 批准：2026-11-18（用户确认 AC-40~AC-49；一次上线，按 feature 逐条提交）
- 日期：2026-11-18
- 依据：`brief.md`、`plan.md`
- 构建顺序：F-15 → F-16 → … → F-23；同一时间只允许一行从 `false` 改为 `true`。
- 切片映射：F-15 ≈ S-01；F-16~F-17 ≈ S-02；F-18~F-22 ≈ S-03；F-23 ≈ S-04。

| ID | Category | Description（端到端行为） | Steps（验证步骤） | AC | Passes | Evidence |
|---|---|---|---|---|---|---|
| F-15 | functional | 两个应用接入 `tokens.css`，删除 `globals.css` 的 `:root` 副本与蓝色字面量；页面仍可登录、聊天、看队列。 | 命令：`pnpm -C apps/chat build && pnpm -C apps/workspace build`；`pnpm -C apps/chat test && pnpm -C apps/workspace test`；手工：启动两个应用，确认颜色/字体变了、布局未变，登录/聊天/队列可用；截图与 S1 前对照。 | AC-40 | false | 2026-11-18：chat/workspace build 通过；vitest 19 + 17 passed；`check-tokens.sh` 通过；跨目录 `@import` 被 Next 拒绝后启用本地副本 + 校验。待评审后改 true。 |
| F-16 | ui | 客户登录页与基线一致：品牌区 + 表单卡、限速提示、密码可见切换、错误 `role="alert"`、开发环境测试账号提示。 | 命令：`pnpm -C apps/chat exec vitest run -t "AC-41"`；手工：`/login` 用 `customer_a` 登录→进入 `/chat`；错误密码→看到 `role="alert"` 文案；点击眼睛切换密码；截图与 `baseline/2026-11-18-customer-login.png` 比对。 | AC-41 | false | 2026-11-18：LoginPanel 5 passed、typecheck/build 通过；密码切换 aria-label 已覆盖；基线比对待 S4。 |
| F-17 | ui | 客户聊天页与基线一致：品牌栏、用户/AI 气泡、欢迎卡、等待卡、三态；转人工时显示等待状态与说明（不估算位次/秒数）。 | 命令：`pnpm -C apps/chat exec vitest run -t "AC-42"`；手工：发消息→AI 回复；发“转人工”→看到等待卡（秒数/位次）；刷新/断网→看到加载与错误态；截图与 `baseline/2026-11-18-customer-chat.png` 比对。 | AC-42 | false | 2026-11-18：ChatShell 9 + SessionGate 6 passed；typecheck/build 通过；等待卡按修订 AC-42 不显示秒数；基线比对待 S4。 |
| F-18 | ui | 坐席登录页与基线一致：品牌区 + 表单卡、环境标识、审计声明、保持登录 8 小时、错误 `role="alert"`。 | 命令：`pnpm -C apps/workspace exec vitest run -t "AC-43"`；手工：`/login` 用 `agent_1` 登录→进入 `/queue`；错误密码→`role="alert"`；截图与 `baseline/2026-11-18-agent-login.png` 比对。 | AC-43 | false | 2026-11-18：LoginPanel 4 passed、workspace 全量 18 passed；typecheck/build 通过；固定 8 小时为展示项；基线比对待 S4。 |
| F-19 | ui | 坐席队列与基线一致：固定列宽、选中/超时行、tab 计数、原因筛选、等待排序、键盘流、409 提示与刷新、批量领取禁用说明。 | 命令：`pnpm -C apps/workspace exec vitest run -t "AC-44"`；手工：两个客户转人工→`agent_1` 看队列；按 `J/K` 移动、`Enter` 领取、`⌘K` 搜索、`Esc` 关闭详情；并发领取→409 提示并刷新；截图与 `baseline/2026-11-18-agent-console.png` 比对。 | AC-44 | false | 2026-11-18：QueueGate 12 passed（含键盘/选中/409/404）；workspace 20 passed；typecheck/build 通过。 |
| F-20 | ui | 详情面板与基线一致：客户块、三指标、脱敏末条、领取规则；完整上下文由 F-08 承接；领取成功进入会话页；无权限不展示数据。 | 命令：`pnpm -C apps/workspace exec vitest run -t "AC-45"`；手工：选中一行→右栏显示详情；点“领取会话”→进入 `/conversations/[id]`；用无权限账号访问→不显示数据。 | AC-45 | false | 2026-11-18：右栏摘要与领取用例通过；完整上下文按修订 AC-45 领取后置灰。 |
| F-21 | ui | 队列四态与基线一致：加载骨架保留列宽、空态给出下一步、错误保留错误码与重试、403 与空队列区分。 | 命令：`pnpm -C apps/workspace exec vitest run -t "AC-46"`；手工：断开接口→看到错误态与重试；空队列→看到空态；无权限账号→看到 403；截图与 `baseline/2026-11-18-agent-states.png` 比对。 | AC-46 | false | 2026-11-18：空态、错误态、401 用例通过；骨架与 403 由 QueueStates/QueueFallback 提供。 |
| F-22 | ui | 可访问性、动效、响应式收口：Tab 焦点可见、aria-live/alert、reduced-motion、四档断点无溢出。 | 命令：`pnpm -C apps/chat exec vitest run -t "AC-47" -t "AC-48"`；`pnpm -C apps/workspace exec vitest run -t "AC-47" -t "AC-48"`；手工：只用键盘走完登录/聊天/队列/领取；系统开启“减少动态效果”后复查；1440/1200/900/375 视口各截一张图检查溢出。 | AC-47、AC-48 | false | 2026-11-18：AC-47 选中/Esc 用例通过；AC-48 四档视口待 S4 走查。 |
| F-23 | ui | 视觉回归与规范收口：两应用截图与基线并排比对，差异只有“允许”；新组件用 Tailwind，无 `!important`/id、无硬编码颜色。 | 命令：`./scripts/verify.sh --no-record`；`python3 scripts/trace.py --strict`；手工：按 `baseline/README.md` 截取四个页面与四态，逐页比对并记录差异分类；`grep` 检查新组件无 `#` 色值与 `!important`。 | AC-49 | false | 2026-11-18：ego-browser 登录截图四页并与基线比对，无“需修/阻断”；截图在 evals/reports/002-ui-redesign/s4/。 |

## 规则

- 一行 = 一个可独立演示的端到端行为；只改一层的拆成任务卡，不占一行。
- `Steps` 必须可执行并给出可观察结果；没有命令/步骤的行退回重拆。
- `Passes` 初始 `false`；`Steps` 全绿且 `Evidence` 非空后才改 `true`。
- `Evidence` 写命令输出摘要、测试名、截图/录像路径、commit；不得手写“已验证”。截图放 `evals/reports/002-ui-redesign/`。
- 不得为了让测试通过而改 `Description`/`Steps`/`AC`；要改先改 `brief.md`/`plan.md` 并重新评审。
- F-15 必须先完成；F-16/F-17 与 F-18~F-21 可并行开发，但按顺序合入；F-22/F-23 最后收口。
- 每行对应一张执行卡，见 `docs/templates/task-design-card.md`；建卡前不得开工。
