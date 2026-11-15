# 当前项目状态

- 更新日期：2026-11-14
- 项目阶段：M1 订单查询与未发货订单取消（M0 出口条件已满足）
- 当前状态：进行中
- 应用代码：已建立工程骨架（T-01），尚无业务逻辑
- 版本控制：Git 已初始化，`main` 分支；全部文档已提交，工作区干净
- 当前 Milestone：M1 订单查询与未发货订单取消（规格已批准：`docs/specs/001-order-cancel/`）
- 当前工作：T-03 实现完成，待独立评审
- 最近验证：`./scripts/verify.sh` 七项全绿——ruff All checks passed、mypy 12 个文件无问题、pytest 76 passed、文档检查 33 个文件 19 条 AC、前端 lint/typecheck/test 通过

## 本阶段目标

把已有全局评审转化为可持续执行的工程基线：

- 固化产品目标、范围和非目标。
- 固化总体架构、模块边界和工程不变量。
- 明确 M1 业务闭环、状态机、接口和验收用例。
- 建立 AI Coding 的文档读取顺序和完成标准。

## 当前允许的工作

- 审阅和修订产品宪章、架构基线与 M1 规格。
- 审阅 `docs/process/README.md`、工具适配入口和 handoff 机制。
- 补齐 M1 的接口契约、数据模型和技术选型 ADR。
- 为 M1 编写测试清单和模拟业务系统契约。

## 当前不允许的工作

- 直接接入真实订单、支付或物流系统。
- 扩展全渠道、售前导购、营销或完整人工坐席后台。
- 引入多 Agent 自主协作框架。
- 在规格和验收尚未批准时大规模生成业务代码。

## 已完成

- M0 基线：原始评审归档、产品宪章、架构基线、不变量、路线图和 AI Coding 规范已建立。
- ADR-0001 至 ADR-0004 均已批准；M1 四份规格与 19 条验收用例已批准。
- M1 澄清清单 12 条全部关闭；四个阻塞问题已决策并回写四份文档。
- 架构基线补充术语表；`AGENTS.md` 与 `README.md` 不再重复维护阶段状态。
- PostgreSQL 17.12 已安装并运行；PostgreSQL 14 及其数据目录已删除。
- 文档检查脚本与 pre-commit hook 生效；`CURRENT.md` 字段已按规范第 5 节对齐。
- UI 规范、组件参考与结构参考稿已建立并批准。
- T-01 工程骨架完成：后端 uv + FastAPI + Alembic，前端 Next.js + TypeScript strict，七项检查全绿；独立评审的 7 项问题已全部处理。
- 任务清单已修订：T-02 扩写为可执行任务，T-06 提前，网关拒绝测试移交 T-05。
- 流程改进：`ai-coding` 规范新增“定界与就绪”检查；`tasks.md` 明确为任务地图，执行契约以设计卡为准。
- T-02 设计卡已产出，四项需人类决策均已确认（金额整数分、时间存 UTC、状态映射归后端、越权统一错误码）。
- 引入 Spec 开发规范：新增 `docs/process/sdd.md`，固定路径与门禁；目录迁移为 `docs/specs/001-order-cancel/`、`docs/tasks/001-order-cancel/`、`docs/design-system/`、`docs/process/`；检查器扩展为结构校验并完成反向验证。
- 引入 TDD 规范：新增 `docs/process/tdd.md`，约定 seam、红-绿循环与突变检查范围；任务模板与 T-02 执行卡已加入红-绿证据与突变分数要求。
- `docs/process/sdd.md` 与 `docs/process/tdd.md` 已批准（2026-11-14）。
- 环境改进（retro）：门禁分两级（提交快检查、推送完整验证）；pre-commit 接入 ruff 格式与静态检查；`verify.sh` 补格式检查；新增测试命名元测试；执行卡引用路径纳入检查；设计令牌抽为 `docs/design-system/tokens.css`；流程规范补非实现者速览。
- 依赖修正：Starlette 1.10 的 TestClient 改用 `httpx2`，dev 依赖由 `httpx` 换成 `httpx2`，测试输出无警告。
- 规格规范化：`requirements.md` 改为 EARS 与用户故事结构（优先级、独立测试、Given/When/Then），补成功标准、关键实体、假设；`requirements.md` 第 10 节 增加“关联 FR”列；`design.md` 增加两张时序图；`tasks.md` 增加状态总览并细化 T-03 至 T-05。新增 3 条内容检查。
- 评审留痕门禁：执行卡标记完成时必须有 `docs/reviews/<spec>/T-XX.md`，已为 T-01、T-02 补记录并反向验证。
- 内容审计：新增 `tests/unit/test_spec_doc_consistency.py`，把需求状态/表达表/ui 覆盖/AC 编号与代码对齐；补齐界面设计的 `COLLECTING` 承接与 design.md 的契约约定。
- 前端格式检查加 `.prettierignore`，`verify.sh` 从超时恢复到约 5 秒。
- 弃用警告升级为失败：`filterwarnings` 拦截 `StarletteDeprecationWarning`，已反向验证。
- T-02 完成：领域契约 `packages/contracts/schemas/domain.json`、Python 领域类型、10 个取消状态映射、7 个错误码；按红-绿推进，76 个后端测试通过。

## 进行中

- M1 规格规范化改写完成，`requirements.md`、`requirements.md` 第 10 节、`design.md`、`tasks.md` 均为等待评审。

## 阻塞

- 上述四份规格未重新批准前，T-03 不开工。

## 下一步

1. 完成 T-03 独立评审并写评审记录。
2. 依次做 T-04（认证）、T-05（网关）、T-06（Mock OMS 与故障注入）。
3. Foundational 完成后，查询切片（T-09、T-10）与取消切片（T-07、T-08、T-14）可并行。
3. T-02 完成后进入 T-03 契约，随后提前建立 T-06 的故障注入能力。
4. 突变检查自 T-07 起生效，届时建立 `scripts/mutation.sh`。

## 待确认决策

业务与范围：

- 首个交互入口使用简单 Web Chat，不接第三方渠道。
- 模拟 OMS 作为唯一业务系统，真实集成放到后续阶段。

流程与任务（2026-11-14 已确认并写入 `tasks.md`）：

- T-01 的“Tool Gateway 越权拒绝测试”移交 T-05，T-01 只保留 AC 引用完整性与包边界不变量两项。
- T-06（Mock OMS 与故障注入）提前到 T-04 之前，先建故障注入能力。

