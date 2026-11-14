# 电商智能客服 Agent

一个以电商客服为业务场景，验证 Agent 业务执行、可靠性、可观测性和质量评估能力的企业级参考项目。

## 当前状态

项目处于 **M0 项目基线**阶段，正在完成产品宪章、架构基线和第一个可执行规格。应用代码尚未开始。

首版目标是打通：

> 查询本人订单 -> 判断未发货订单能否取消 -> 用户确认 -> 幂等提交 -> 查询结果 -> 异常恢复

退款、全渠道、多 Agent 自由协作和完整运营后台不在 M1 范围内。

## 文档入口

- [当前阶段](docs/CURRENT.md)
- [产品宪章](docs/product/charter.md)
- [总体架构](docs/architecture/overview.md)
- [架构不变量](docs/architecture/invariants.md)
- [路线图](docs/roadmap.md)
- [AI Coding 协作规范](docs/ai-coding/README.md)
- [初始技术评审](docs/reviews/2026-11-14-initial-architecture-review.md)
- [AI Coding 调研](docs/research/ai-coding-new-project-practices-2026-11-14.md)
- [M1 订单取消规格](docs/specs/M1-order-cancel/requirements.md)

## 项目原则

- 先形成全局基线，再派生当前迭代规格。
- 一个主 Agent + 领域 Tool + 确定性 Workflow。
- 模型负责理解和沟通，业务规则和权限由确定性代码执行。
- 回答正确不等于任务完成；以业务结果和评测证据判定成功。
- 原始评审、架构决策、当前规格和验收用例全部版本化保存。

## 切换 AI Coding 工具

工具支持 `AGENTS.md` 时会自动读取入口。Claude Code 和 Gemini CLI 分别使用根目录的 `CLAUDE.md` 与 `GEMINI.md` 作为轻量适配入口。

如果工具不会自动读取项目文件，在首次消息中发送：

```text
请先读取 AGENTS.md、docs/ai-coding/README.md 和 docs/CURRENT.md。
在修改任何文件前，用五项摘要确认：当前阶段、已完成、进行中、阻塞、下一步。
```

## 本地运行

工程骨架尚未建立。后续加入真实脚手架时，应在此处和 `AGENTS.md` 中同步安装、运行、测试、Lint 和评测命令。

