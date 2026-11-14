# 当前项目状态

- 更新日期：2026-11-14
- 项目阶段：M1 订单查询与未发货订单取消（M0 出口条件已满足）
- 当前状态：进行中
- 应用代码：尚未开始
- 版本控制：Git 已初始化，`main` 分支；全部文档已提交，工作区干净
- 当前 Milestone：M1 订单查询与未发货订单取消（规格已批准：`docs/specs/M1-order-cancel/`）
- 当前工作：工程基线文档（ADR-0004、ui.md）已起草，待确认后启动 T-01
- 最近验证：PostgreSQL 17.12 `pg_isready` 接受连接、`select version()` 返回 17.12；Markdown 内部链接检查 25 个文件、缺失 0；`git status --porcelain` 提交后无输出

## 本阶段目标

把已有全局评审转化为可持续执行的工程基线：

- 固化产品目标、范围和非目标。
- 固化总体架构、模块边界和工程不变量。
- 明确 M1 业务闭环、状态机、接口和验收用例。
- 建立 AI Coding 的文档读取顺序和完成标准。

## 当前允许的工作

- 审阅和修订产品宪章、架构基线与 M1 规格。
- 审阅 `docs/ai-coding/README.md`、工具适配入口和 handoff 机制。
- 补齐 M1 的接口契约、数据模型和技术选型 ADR。
- 为 M1 编写测试清单和模拟业务系统契约。

## 当前不允许的工作

- 直接接入真实订单、支付或物流系统。
- 扩展全渠道、售前导购、营销或完整人工坐席后台。
- 引入多 Agent 自主协作框架。
- 在规格和验收尚未批准时大规模生成业务代码。

## 已完成

- 原始架构评审已原样归档。
- 产品宪章、架构基线、不变量和路线图草案已建立。
- M1 订单取消需求、设计、任务和验收草案已建立。
- ADR 已统一到 `docs/adr/`。
- 跨工具 AI Coding 协作规范和 handoff 机制已建立。
- M0 文档基线已纳入 Git 版本控制（此前仅 `README.md` 被跟踪，其余文件处于未跟踪状态）。
- AI Coding 规范 4.6 补充提交要求：`CURRENT.md` 的更新与本次变更须进入同一次提交。
- `docs/ai-coding/README.md` 已确认并标为已批准（2026-11-14）。
- `CURRENT.md` 字段已按规范第 5 节对齐：补齐"当前 Milestone"，统一"项目阶段""当前状态"命名。
- ADR-0001、ADR-0002、ADR-0003 已确认为已批准（2026-11-14，无保留意见）。
- M1 四个阻塞问题已决策并回写四份文档：资格以 Policy Engine 为唯一权威；取消任务在表达意图时创建并允许转入 `ABANDONED`；补齐 `SUBMITTING`/`SUBMIT_UNKNOWN` 的"已提交"表达；技术清单与业务清单分层维护。同步新增 AC-19。
- 架构基线补充第 10 节术语表，定义 OMS、Mock OMS、Tool、Tool Gateway、Workflow、Agent Runtime、幂等键和租户。
- M1 需求、设计、任务、验收四份文档已标为已批准（2026-11-14）；AC-02 收紧为"不调用 OMS，统一返回查无此单"。
- M0 出口条件已满足：规格与 19 条验收用例全部确认。

## 进行中

- M1 澄清清单 `docs/specs/M1-order-cancel/clarifications.md` 已建立，共 12 条待答复。
- 已完成 AI Coding 人机协作流程调研，见 `docs/research/ai-coding-dev-collaboration-2026-11-14.md`。
- 已采纳 4 项流程门禁：任务设计卡（`docs/templates/task-design-card.md`）、独立评审、T-01 加三项可执行检查、澄清清零后才开工。
- PostgreSQL 17.12 已安装并以 Homebrew 服务运行，连接验证通过；PostgreSQL 14 及其数据目录已删除。

- 澄清清单 12 条已全部关闭，答复与写回位置逐条记录在 `docs/specs/M1-order-cancel/clarifications.md`。
- T-01 任务设计卡已产出：`docs/specs/M1-order-cancel/design-cards/T-01.md`，含 4 个待答问题。
- 新增 `scripts/check-docs.py` 与 `.githooks/pre-commit`：自动检查链接、状态词、CURRENT 字段、AC 覆盖与设计卡门禁。
- `AGENTS.md` 与 `README.md` 不再重复维护阶段状态，统一以本文件为唯一来源。
- 新增 `ui-mockup.html` 结构参考稿，画出六个界面状态；`ui.md` 增加第 9 节说明其用途与冲突处理。

## 阻塞

- `docs/adr/0004-engineering-baseline.md` 仍为拟议、`ui.md` 仍为草案，T-01 设计卡因此保持待确认；检查脚本已能拦截这类状态。

## 下一步

1. 批准 `docs/adr/0004-engineering-baseline.md` 与 `docs/specs/M1-order-cancel/ui.md`。
2. 将 T-01 设计卡状态改为待开工许可，并跑通 `python3 scripts/check-docs.py`。
3. 执行 T-01，记录六条验证命令的真实输出，并交由独立评审。

## 待确认决策

业务与范围待确认项只在本节维护；技术选型见 `docs/specs/M1-order-cancel/design.md` 第 10 节。

- 首个交互入口使用简单 Web Chat，不接第三方渠道。
- 模拟 OMS 作为唯一业务系统，真实集成放到后续阶段。

