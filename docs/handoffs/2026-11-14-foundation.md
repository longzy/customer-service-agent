# Handoff：项目基线与 AI Coding 规范

- 时间：2026-11-14
- 当前阶段：M0 项目基线
- 当前状态：等待评审
- 应用代码：尚未开始
- 版本控制：尚未初始化 Git
- 更正（同日后补）：写本文时 Git 已初始化但文档尚未被跟踪；此字段已过时，实时状态以 `docs/CURRENT.md` 为准。本文其余内容保留为当时快照。

## 本次目标

建立可持续的 AI Coding 项目基线和跨会话恢复机制。

## 已完成

- 初始架构评审原样归档到 `docs/reviews/2026-11-14-initial-architecture-review.md`。
- 建立产品宪章、总体架构、不变量和路线图草案。
- 建立 M1 订单取消需求、设计、任务和验收草案。
- 将 ADR 统一到 `docs/adr/`。
- 建立 `AGENTS.md`、`docs/process/README.md`、`CLAUDE.md` 和 `GEMINI.md` 的可移植入口。
- 将实时项目状态集中在 `docs/CURRENT.md`。

## 未完成

- AI Coding 规范尚未经过用户最终确认。
- M1 的交互、接口、技术栈和前端架构尚未批准。
- 应用工程骨架和业务代码尚未开始。

## 关键决策

- 仓库是项目状态的唯一事实源，见 `docs/adr/0003-repository-source-of-truth.md`。
- 原始评审不改写，后续结论写入现行架构、ADR 或 Spec。
- 根指令文件只做路由，详细规范保存在 `docs/ai-coding/`。

## 最近验证

- 使用 `cmp` 验证原始评审归档与附件逐字节一致，退出码为 0。
- 使用 `rg` 确认旧的 ADR 目录引用与目录均已移除。
- 使用 Markdown 链接检查脚本检查 20 个文件，内部链接缺失数为 0。
- 当前没有应用代码，因此没有构建或业务测试结果。

## 当前阻塞

无。

## 下一位 Agent 的下一步

1. 阅读 `AGENTS.md`、`docs/process/README.md` 和 `docs/CURRENT.md`。
2. 核对本 handoff 与 `CURRENT.md` 是否一致。
3. 按用户指令审阅 AI Coding 规范；不要自行恢复 M1 开发。

## 涉及文件

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `docs/process/README.md`
- `docs/CURRENT.md`
- `docs/adr/`
- `docs/specs/M1/001-order-cancel/`

