# 前端代码规范（FE）

- 状态：草案
- 批准：待双轴评审后升为已批准
- 日期：2026-11-18
- 适用：`apps/chat`（客户）、`apps/workspace`（坐席）、`packages/contracts` 生成物
- 关联：[工程标准](standards.md)、[UI 规范](../design-system/ui-spec.md)、[ADR-0007](../adr/0007-openapi-frontend-types.md)
- 强制点：见第 10 节；未接门禁的条目由评审清单兜底，不写成“看起来像标准”的建议。

## 0. 现状前提

本规范按仓库事实制定，不做理想化假设：

- Next.js 16.4 App Router（Turbopack 默认；`next lint` 已移除，lint 走 ESLint CLI + flat config）；两个应用各自独立 `pnpm-lock.yaml`，根目录没有 workspace。
- **决策（2026-11-18）：不建跨应用共享包，组件重复允许。** 两个应用各自维护 `features/`、`components/` 与 `lib/`；同一应用内重复 ≥2 次才抽公共层。
- 现状（2026-11-18 迁移后）：`app/` 只装配；组件、请求与类型已落到 `features/auth`、`features/chat`（chat）与 `features/auth`、`features/queue`、`features/conversation`（workspace）；`components/ui`、`components/layout` 尚未抽出。样式仍是 `app/globals.css` 全局类名；`tokens.css` 只有颜色，没有间距/圆角/字号令牌。
- **迁移原则**：新代码遵守本规范；样式与 token 存量在改动时渐进迁移，不做一次性重构。

## 1. 目录与模块（FE-DIR）

目标结构（每个应用一份）：

```text
app/                     路由与装配，只放 page/layout/error/not-found
features/<feature>/      按功能组织
  components/            业务组件（含 ui 组合）
  hooks/                 该 feature 的状态与数据 hook
  api/                   请求函数（可调用 lib/api-client）
  types/                 该 feature 的本地类型
  index.ts               唯一对外出口
components/ui/           跨 feature 的纯展示原子组件
components/layout/       区域骨架（Shell/Rail/页头）
lib/                     跨 feature 的基础设施（api client、format、session）
tests/                   组件测试
```

- **FE-DIR-01** `app/` 只做装配：`page.tsx` 不写业务逻辑、不直接请求、不定义超过 10 行 JSX 的区块，复杂内容放 `features/`。
- **FE-DIR-02** 新功能必须落在 `features/<feature>/`，不得继续往 `components/` 根目录平铺新文件（`components/ui`、`components/layout` 除外）。
- **FE-DIR-03** 依赖方向：`app → features/*/index → features 内目录 → components/ui、lib`。`components/ui` 不得 import 任何 feature 或业务 lib；features 之间不得互相 import，共享逻辑上提到 `components/` 或 `lib/`。
- **FE-DIR-04** `features/<f>/index.ts` 只做 re-export，不写逻辑；`app/` 只能从 `features/<f>` 的 index 导入，禁止深引用 `features/<f>/components/xxx`。
- **FE-DIR-05** 单文件上限：组件 250 行、hook/util 200 行、测试 400 行、CSS 300 行。超过必须拆分，不得靠压缩空行规避。
- **FE-DIR-06** 命名：组件文件 `PascalCase.tsx`，hook `useCamelCase.ts`，feature 目录 `kebab-case`，lib `camelCase.ts`；样式文件与组件同名。
- **FE-DIR-07** 组件默认 named export；`app/**/page.tsx`、`layout.tsx` 按 Next 约定 default。一个文件只导出一个组件。
- **FE-DIR-08** 新增组件/hook 前必须先查重：在 `components/`、`features/*/components`、`features/*/hooks`、`lib/` 搜索同名导出与相近职责；能复用或扩展的，优先改现有实现，不新建。提交说明写明“已查重”。
- **FE-DIR-09** 抽公共层的门槛：同一应用内出现第 2 个使用方时才上提（`components/` 或 `lib/`）；只有 1 个使用方时留在 feature 内，避免过度抽象。

## 2. 组件（FE-CMP）

- **FE-CMP-01** `components/ui` 判定：无业务语义、无请求、无路由、无固定文案（文案由 props 传入）。任一不满足即为业务组件。
- **FE-CMP-02** 业务组件可持有交互状态（展开、输入、选中），**不得直接请求接口**；请求放 `features/*/hooks` 或 `features/*/api`。
- **FE-CMP-03** 一个组件只做一件事；布尔开关不超过 1 个，出现第 2 个必须改为 variants 或拆分。
- **FE-CMP-04** props 超过 5 个时，优先组合（`children` / 子组件）或拆分；保留则在执行卡写明理由。
- **FE-CMP-05** 互斥状态用判别联合，禁止 3 个以上互斥布尔量（`isLoading` + `isError` + `isEmpty` 视为反例）。
- **FE-CMP-06** 事件 prop 用 `onXxx`；布尔 prop 用 `is/has/can` 前缀；禁止透传 `...rest` 到业务组件。

## 3. 类型与数据（FE-DATA）

- **FE-DATA-01** 接口类型只能来自 `lib/api-types.ts`（OpenAPI 生成），禁止手写后端字段；生成物禁止手改。
- **FE-DATA-02** 请求统一走 `lib/` 的 api client，组件内禁止出现裸 `fetch` 与硬编码接口 URL。
- **FE-DATA-03** 错误统一为 `ApiError`（status/code/message）；界面只展示兜底文案，不直出后端 `detail`。
- **FE-DATA-04** 金额以整数分传输，展示时格式化；时间以 UTC ISO 8601 接收，展示统一走格式化工具。新增格式化函数放 `lib/format.ts`，禁止散落 `toLocaleString()`。
- **FE-DATA-05** 禁止 `any`；`unknown` 必须窄化后使用；禁止无理由的 `@ts-ignore` / `as unknown as`。
- **FE-DATA-06** 组件 props 必须显式类型并导出；`children` 显式标注 `ReactNode`。

## 4. Next.js 边界（FE-NEXT）

- **FE-NEXT-01** 默认 Server Component；`"use client"` 只加在需要交互的最小叶子文件，禁止加在 `layout.tsx`。
- **FE-NEXT-02** 禁止在 Next 中新建 Route Handler 代理业务接口（后端是 FastAPI，边界见 [架构总览](../architecture/overview.md)）；确需代理必须走 ADR。
- **FE-NEXT-03** 新增或改动数据请求的页面必须同时提供 loading、empty、error 三态，并补 `app/error.tsx`；存量页面在下次改动时补齐。
- **FE-NEXT-04** 环境变量只有显式允许的才可用 `NEXT_PUBLIC_` 前缀；其余只在服务端读取。

## 5. 样式与设计令牌（FE-CSS）

- **FE-CSS-01** 令牌单一来源是 `docs/design-system/tokens.css`；`app/globals.css` 里的 `:root` 颜色副本是历史债，迁移完成前禁止再新增颜色字面量。
- **FE-CSS-02** 新增样式优先用令牌；尚无令牌时使用 4px 基数的间距（2/4/6/8/12/16/24/32），禁止 5/7/9/10/14 这类非标值。ui-spec 组件契约中明确写出的固定尺寸（如订单卡片 7px 状态圆点、空态 44px 圆形图标）按契约执行，不受本条间距基数约束；未写入契约的历史值（如 18/26）不作为新增依据。
- **FE-CSS-03** 颜色只能出现在 `tokens.css` 与 `globals.css` 的 `@theme`；新样式一律用 Tailwind utility（颜色/字号/圆角取 theme 映射），禁止新增全局选择器与新的 `.module.css`。
- **FE-CSS-04** 状态不得只靠颜色表意，必须同时有文字或图标。
- **FE-CSS-05** UI 组件库仅允许 HeroUI v3（`@heroui/react` + `@heroui/styles`，样式在 `globals.css` 中于 `@import "tailwindcss"` 之后引入）；图标库仅允许 `lucide-react`，不得引入第二套 UI/CSS 框架、图标库或远程字体；通用图标用 lucide 组件，品牌图形等无对应图标保留内联 SVG，颜色继承 `currentColor`。
- **FE-CSS-06** 样式承载、动效、响应式与视觉基线以 [ui-spec 2.6–2.9](../design-system/ui-spec.md) 为准；Tailwind 仍是唯一的样式编写方案，HeroUI v3 自带的组件样式按 FE-CSS-05 引入、不算第二套方案；组件级定制只用 `className` 的 Tailwind utility，禁止全局 BEM 选择器覆盖；不得引入 styled-components/Emotion 等 CSS-in-JS 或新的 CSS Modules。

## 6. 可访问性（FE-A11Y）

- **FE-A11Y-01** 交互元素用原生 `button`/`a`/`input`，禁止用 `div` 加点击。
- **FE-A11Y-02** 焦点可见（`:focus-visible`），禁止 `outline: none` 无替代。
- **FE-A11Y-03** 消息流用 `aria-live="polite"`；错误提示用 `role="alert"`。
- **FE-A11Y-04** 图标必须配文字、`aria-label` 或 `aria-hidden`，不单独承载语义。
- **FE-A11Y-05** 键盘可完成主流程（发送、领取、关闭）；新增交互必须说明键盘路径。

## 7. 安全（FE-SEC）

- **FE-SEC-01** 禁止 `dangerouslySetInnerHTML`。
- **FE-SEC-02** 令牌与会话信息禁止写入 `localStorage` / `sessionStorage`；认证只依赖 HttpOnly Cookie。
- **FE-SEC-03** 禁止在客户端代码中出现内部地址、密钥、租户标识。
- **FE-SEC-04** 外链必须 `rel="noopener noreferrer"`；`target="_blank"` 需给出原因。

## 8. AI 生成专项（FE-AI）

- **FE-AI-01** 禁止 import 未在 `package.json` 声明的依赖；新增依赖必须单独提交并说明理由。
- **FE-AI-02** 禁止猜测接口字段、状态码或错误结构；以 `lib/api-types.ts` 与后端契约为准。
- **FE-AI-03** 禁止为通过测试而删除/弱化断言、加 `skip`、改 mock 掩盖失败。
- **FE-AI-04** 禁止顺手重构执行卡之外的文件；单次改动只碰执行卡列出的文件。
- **FE-AI-05** 注释只写“为什么”，禁止复述代码、禁止留“TODO: 实现”占位。
- **FE-AI-06** 禁止用 `console.log` 提交调试输出。
- **FE-AI-07** 生成代码必须能通过 `next build`；不得以“本地能跑”替代构建验证。

## 9. 测试（FE-TEST）

- **FE-TEST-01** 组件测试用 Testing Library，按 `role` / `label` / 文本查询；禁止 `container.querySelector`。
- **FE-TEST-02** 禁止大型快照；只对稳定的小结构做快照。
- **FE-TEST-03** mock 网络层而非业务模块；`vi.mock` 只允许用于路由、时间、随机数等不可控依赖。
- **FE-TEST-04** React `act()` 警告视为失败，不得忽略。
- **FE-TEST-05** 前端测试的 AC 追溯已接入 `scripts/trace.py`：测试文件头写 `// AC-XX`（或用例名含 `AC-XX`）；按文件计入覆盖，不区分用例数。
- **FE-TEST-06** mock 的 `useRouter`/`useSearchParams` 必须返回模块级稳定引用。依赖 router 的 `useCallback`/`useEffect` 会因每次渲染的新对象反复重跑；在同步渲染下会耗尽堆内存（vitest 报 worker OOM 而非测试失败）。

## 10. 强制点与缺口

| 规则 | 强制点 | 状态 |
|---|---|---|
| FE-DATA-01 生成物不可手改 | `scripts/check-contracts.sh`（verify + pre-commit） | 已接入 |
| FE-DATA-01 类型一致性 | `pnpm typecheck`（verify） | 已接入（仅类型） |
| 核心 lint（React/Hooks/Next 基础规则） | `pnpm lint` → `eslint .`（ESLint 9 flat config；verify + CI） | 已接入 |
| FE-DATA-05 禁 any | `eslint-config-next/typescript` 的 `@typescript-eslint/no-explicit-any`（warn） | 已接入（warn） |
| FE-DATA-02 请求集中到 lib | 无 | 待接 `no-restricted-syntax` 或脚本 |
| FE-CMP-01..06、FE-DIR-01..05、08..09 | 无 | 待接 ESLint（`max-lines`、`import/no-restricted-paths`） |
| FE-DIR-06/07 组件命名与单组件 | `scripts/check-review-prereqs.py`（pre-commit + verify） | 已接入（命名/单组件；目录/查重仍人工） |
| FE-CSS-02/03 颜色与 token | `./scripts/lint-styles.sh`（stylelint：`color-no-hex`、`declaration-no-important`、`selector-max-id`；verify + CI） | 已接入 |
| FE-A11Y-01..05 | 无 | 待接 `plugin:jsx-a11y/recommended` |
| FE-SEC-01/02 | 无 | 待接 `no-restricted-syntax` |
| FE-AI-01 依赖幻觉 | 无 | 待接 `import/no-extraneous-dependencies` |
| FE-TEST-01..04 | 无 | 待接测试脚本 |
| FE-TEST-05 前端 AC 追溯 | `scripts/trace.py` 读取 `apps/*/tests` 文件头 `// AC-XX`（pre-commit/verify） | 已接入 |
| FE-TEST-06 路由 mock 稳定引用 | ESLint `no-restricted-syntax`（`tests/**`；`pnpm lint`，verify + CI） | 已接入 |
| 未接入项 | 评审清单 Standards 轴 | 人工 |

接入顺序建议：ESLint 与 stylelint 已接入 → 前端快检查进 pre-commit → 测试与追溯。每接一条，把对应行改为“已接入”并给出脚本入口。

## 11. 存量豁免

在对应迁移完成前，下列文件豁免标注的规则，但**改动时不新增违规**：

- `apps/chat/app/globals.css`、`apps/workspace/app/globals.css`：豁免 FE-DIR-05、FE-CSS-01、FE-CSS-03（`:root` 颜色副本，令牌迁移时删除）。
- 两个应用各自实现的 `LoginPanel` 等相同组件：按 0 节决策，重复允许，不要求合并。

豁免清单只减不增；新增豁免需在评审记录里写明原因与移除条件。

## 变更记录

- 2026-11-18：草案建立。依据用户确定的“只出规范、不做代码与配置改动；两个应用各自维护、允许重复”落地；列出现状缺口与强制点接入顺序。
- 2026-11-19：接入 stylelint（两个应用各自 devDependency 与 `.stylelintrc.json`），`scripts/lint-styles.sh` 进 verify/CI；强制 tokens 外无颜色字面量、无 `!important`、无 id 选择器。
- 2026-11-18：两个应用升级 Next.js 16.4（React 19.3；`next lint` 移除后改用 ESLint CLI + flat config）；组件、请求与类型迁入 `features/`，`app/` 只装配；`ChatShell` 拆出 `useChatMessages`，FE-DIR-05 豁免移除；核心 lint 接入 verify 与 CI。两个应用暂时关闭 `react-hooks/set-state-in-effect`（存量 gate 在 effect 内拉数据并 setState），迁到数据获取层后删除该例外。
- 2026-11-20：按用户决策接入 HeroUI v3（`@heroui/react` + `@heroui/styles` 3.2.7），修订 FE-CSS-05/06：HeroUI 成为唯一允许的 UI 组件库，Tailwind 仍是唯一样式编写方案。`globals.css` 中 `@heroui/styles` 排在 `@import "tailwindcss"` 之后、`tokens.css` 之前，使项目令牌覆盖同名变量、保持视觉基线；其自带样式属外部依赖，不计入 FE-CSS-03 的项目内颜色字面量约束。主题策略：项目令牌仍是单一事实源，不启用 HeroUI 默认主题，只在 `tokens.css` 映射其根变量；HeroUI 组件由 `@apply` 写死的尺寸/圆角/动效在首次落地组件时用 `className` 的 Tailwind utility 约束，不预先建 wrapper、不写全局 BEM 覆盖。
- 2026-11-22：新增 FE-TEST-06 并接入 ESLint `no-restricted-syntax`：测试中的 `useRouter` mock 必须返回模块级稳定对象。F-30 曾因内联 mock 每次渲染产生新 router，导致依赖 router 的 effect 同步死循环、vitest worker OOM。chat 的 vitest worker 同时限制堆上限，让同类问题更快暴露。
- 2026-11-22：澄清 FE-CSS-02 的适用范围：4px 基数约束布局间距，ui-spec 组件契约明确写出的固定尺寸（订单卡片 7px 圆点、空态 44px 图标）优先。F-30 评审中 Standards 与 Spec 两轴曾因 7px 圆点给出冲突结论。
- 2026-11-22：FE-TEST-05 落地：`trace.py` 在前端测试文件头读取 `// AC-XX`（前 5 行），与用例名扫描合并去重；P2 起前端行为类 AC 不再只靠后端测试计数。
