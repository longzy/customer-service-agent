# UI 改版 plan

> 结构依据：Google Design Doc（Context and Scope / Goals and Non-Goals / The Design / Alternatives Considered / Cross-cutting Concerns）。
> 页数：T2，约 3 页；只写关键约束，不抄组件实现。

- 状态：已批准
- 批准：2026-11-18（用户确认 AC-40~AC-49；一次上线，按 feature 逐条提交）
- 日期：2026-11-18
- 作者 / 评审者：实现者 / 待独立评审
- 依据：`brief.md`、[ui-spec](../../design-system/ui-spec.md) v4、[设计稿](../../design-system/proposals/README.md)、[基线](../../design-system/baseline/README.md)
- 规模：T2（两个前端应用、视觉重构；不改领域/权限/状态机）

## 1. 背景与范围（Context and Scope）

- 问题与现状：`apps/chat` 与 `apps/workspace` 仍是原型样式，`globals.css` 各自维护 `:root` 副本与蓝色字面量；客户侧没有等待反馈，坐席侧是单列卡片队列，没有列宽、超时与键盘流。
- 为什么现在做：设计稿、令牌、组件契约与视觉基线已于 2026-11-18 冻结；后续切片会继续叠加旧样式，越晚改越贵。
- 本设计覆盖：S1 令牌接入、S2 客户侧（登录 + 聊天）、S3 坐席侧（登录 + 队列 + 详情 + 四态 + 键盘流）、S4 视觉回归收口。
- 本设计不覆盖：后端、API、权限、状态机、移动端新设计、暗色模式、i18n、跨应用共享组件包。
- 相关 ADR / 不变量：[ADR-0006](../../adr/0006-customer-login.md)（登录方式不变）、[ADR-0007](../../adr/0007-openapi-frontend-types.md)（类型仍来自生成物）、[前端规范](../../process/frontend.md)、`docs/design-system/ui-spec.md`。

## 2. 目标与非目标（Goals and Non-Goals）

### Goals

- 两应用的登录页、聊天页、队列页与基线截图一致，差异只允许“字体抗锯齿”类。
- 令牌单一来源：`globals.css` 不再定义颜色/字体；新组件只用 `tokens.css` 与 CSS Modules。
- 客户侧等待卡、坐席侧超时/四态/键盘流可用，且状态不靠颜色单独表达。
- 四档断点下无横向溢出、无信息丢失，坐席表格不压列宽。
- 前端测试与 AC 可追溯，`trace.py --strict` 通过。

### Non-Goals

- 不改任何接口、字段、错误码与权限判断。
- 不引入状态库、UI 库、图标库、CSS 框架或新依赖。
- 不做移动端专属设计（只按 ui-spec 2.8 重排）；不做暗色与 i18n。
- 不再调整 `features/` 边界（目录重构已于 2026-11-18 完成，见 [frontend.md](../../process/frontend.md)）；本切片只在既有 feature 内拆分展示组件。

## 3. 方案（The Design）

### 3.1 目录与组件拆分

两个应用各自实现，不建共享包（已批准决策）。目录已在 2026-11-18 迁到 `features/`，本切片在既有 feature 内拆分组件，不调整 feature 边界。

- `apps/chat/features/auth/`：`LoginPanel`；`apps/chat/features/chat/`：`ChatShell`、`BrandPanel`、`MessageList`、`MessageBubble`、`Composer`、`HandoffCard`、`ErrorState`；跨 feature 原子组件放 `components/ui/`（`Button`、`Field`、`Chip`、`Kbd`）。
- `apps/workspace/features/`：`auth`（`LoginPanel`）、`queue`（`QueueToolbar`、`QueueTable`、`StatusBadge`、`EmptyState`、`ErrorState`）、`conversation`（`WorkspaceShell`、`DetailPanel`、`DeniedState`）；跨 feature 原子组件放 `components/ui/`。
- `ChatShell` 已拆出 `useChatMessages`（2026-11-18）；本切片继续拆分展示组件，迁移后每个文件 ≤250 行（测试 ≤400）。

### 3.2 令牌接入（S1）

首选：`apps/*/app/globals.css` 顶部

```css
@import "../../../docs/design-system/tokens.css";
```

- 路径从 `apps/chat/app/` 上三级到仓库根；Next/PostCSS 若拒绝项目根外文件，S1 暂停并改用回退方案。
- 回退：`scripts/check-tokens.sh` 比较 `docs/design-system/tokens.css` 与 `apps/*/app/tokens.css` 的哈希，禁止漂移；同步由脚本完成，`tokens.css` 仍是唯一源。
- 实施注记（2026-11-18）：首选方案实测被 Next 15 拒绝（`Module not found: Can't resolve '../../../docs/design-system/tokens.css'`），已启用回退；`check-tokens.sh` 接入 `verify.sh` 与 pre-commit。
- 同时删除两个 `globals.css` 的 `:root` 副本，字体栈改 `var(--font-sans)`，蓝色字面量（`#2563EB`、`rgba(37,99,235,…)`、`#EFF6FF` 等）清零。
- 存量全局类名保留到 S2/S3；S1 只换令牌，不改布局，便于单独回滚。

### 3.3 样式承载

- 新组件一律 Tailwind utility；颜色/字号/圆角由 `@theme` 映射 tokens；全局只留 Tailwind 入口、`@theme` 与 `html/body` 排版。
- 共享原子组件在各自 `components/ui/` 内实现（不跨应用共享），样式同样用 Tailwind。
- 禁止 `!important`、id 选择器、超过 2 层标签嵌套；动态内联样式只允许数值（如进度宽度）。

### 3.4 页面、路由与数据

- 路由不变：`/login`、`/chat`、`/queue`、`/conversations/[id]`。
- 客户登录成功 → `/chat`；坐席登录成功 → `/queue`；领取成功 → `/conversations/[id]`。
- 详情右栏是队列页内的预览，不新增路由、不新增 Route Handler。
- 复用 `lib/session.ts`、`lib/queue.ts`、`lib/conversation.ts`；不改 fetch 与错误映射；不引入状态库。

### 3.5 交互与状态

- 客户侧：加载/空/错误三态；等待卡显示转人工状态与说明（客户会话接口只有状态，不返回秒数/位次，禁止前端估算）；轮询逻辑不变。
- 坐席侧：tab 计数、原因筛选、等待排序在前端内存完成（数据量小，服务端 FIFO 顺序不变）；超时阈值 5 分钟为前端展示规则，不改后端。
- 键盘流：`J/K` 移动选中、`Enter` 领取、`⌘K` 聚焦搜索、`Esc` 关闭详情、`?` 打开快捷键面板；输入框聚焦时不拦截按键。
- 409/404 继续走现有提示与刷新逻辑，不改文案语义。

### 3.6 可访问性、动效与响应式

- 按 ui-spec 第 5 节与 2.7/2.8：焦点可见、`aria-live="polite"`、`role="alert"`、图标 `aria-hidden`、状态文字 + 圆点。
- 动效仅限入场 240ms、状态 120ms、脉冲/spinner；`prefers-reduced-motion` 移除入场与脉冲。
- 断点用 `max-width`/`min-width` 成对书写；坐席表格横向滚动，不压列宽；<768 坐席只读。

### 3.7 测试与追溯

- 前端测试用 Testing Library，按 role/label 查询；测试名带 `AC-XX`（如 `it("AC-41 客户登录…")`）。
- 扩展 `scripts/trace.py`：测试扫描范围加入 `apps/*/tests`（排除 `node_modules`），让前端 AC 进入追溯；不改 001 的既有判定。
- 现有测试按旧结构查询会失效，必须同步更新断言，禁止删除断言或跳过用例。
- 每条 feature 的 Steps 给出可执行命令与可观察结果。

### 3.8 视觉验收

- S4 按 [baseline/README](../../design-system/baseline/README.md) 固定视口截图，与基线并排比对；差异分“允许/需修/阻断”。
- 截图存 `evals/reports/002-ui-redesign/`（已 gitignore），Evidence 写路径摘要。

## 4. 备选方案（Alternatives Considered）

| 方案 | 否决理由 |
|---|---|
| 一次改完两应用 | 评审、验收、回滚都不可控，且违反“一次一个 feature” |
| 建 `packages/ui` 共享组件 | 已批准两应用各自维护；跨应用共享会引入 workspace 与构建变更 |
| 继续用全局类名 | 与 ui-spec 2.6 冲突，后续组件样式互相污染 |
| 复制 `tokens.css` 到各应用 | 双源会漂移；仅作为 S1 的回退方案，并加一致性检查 |
| 引入 Tailwind/UI 库 | 与“不引入 UI 库”及现有 CSS 体系冲突 |

## 5. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| Next 拒绝跨目录 `@import` | S1 无法按首选方案接入 | S1 先验证 `build`；失败改用同步脚本 + 哈希检查 |
| 组件拆分导致行为回归 | 客户/坐席流程不可用 | 每步保留既有测试并补充 role 查询；S2/S3 独立回滚 |
| 视觉与基线偏差 | 验收不通过 | S4 并排比对；先修代码不改基线 |
| 响应式引入布局溢出 | 窄屏不可用 | 四档视口走查；表格横向滚动 |
| 前端测试数量少于 AC | trace 无法覆盖 | 测试名带 AC；扩展 trace 扫描 `apps/*/tests` |

## 6. 交叉关注（Cross-cutting Concerns）

- 安全：登录错误文案不区分“账号不存在/密码错误”；不新增存储；不把会话写入 localStorage。
- 性能：不新增依赖；CSS 体积可控；无图片与远程字体。
- 可观测：无新增事件；保留现有审计与错误码。
- 回滚：S2、S3 各自可回滚到上一提交；S1 只改令牌，回滚无数据影响。

## 7. 验收与门禁

- `./scripts/verify.sh --no-record` 全绿（含两应用 lint/format/typecheck/test/build）。
- `python3 scripts/trace.py --strict` 通过；AC-40~AC-49 均被 feature 引用且有测试。
- `python3 scripts/check-docs.py` 通过；S4 基线比对记录进执行卡。
- 实现者不得自审；S2/S3 完成后各做一次独立评审。
