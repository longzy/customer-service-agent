# 评审 checklist（F-xx）

- 适用：T2/T3 的独立上下文评审；T1 可裁剪，但门禁复核与逐 AC 结论保留。
- 输出格式：[review 模板](../templates/review.md)。

## 0. 门禁复核

- 评审范围固定点：本 feature 开工前 HEAD（首个实现提交的父提交，`git rev-parse <first-feat-commit>^`）；记录 `git diff <fixed>...HEAD` 与 `git log <fixed>..HEAD --oneline`。
- 先跑 `make verify-check`；失败直接「不通过」。
- 独立跑该 feature 的 `Steps` 命令（AC 定向测试），不只看实现者粘贴的数字。
- 评审者用独立测试库，避免与实现者的 `customer_service_test` 竞争：`TEST_DB_NAME=customer_service_review_<id> ./scripts/test-db.sh <定向用例> -q`。
- 契约变更检查 `./scripts/check-contracts.sh`。

## Standards 轴

- 文档：`standards.md` 的 STD-*、`invariants.md` 的 INV-01/02/03/07/11/12/16/17/18。
- 边界：`overview.md` 的模块依赖与事务提交归属；api 只编排，conversations/identity 不互相越界。
- 安全：身份只来自认证上下文、越权 404、Cookie/密钥/日志脱敏。
- PII/脱敏：核对实现声明的支持格式矩阵（手机 `+86`/分隔/全角、邮箱、身份证 `X/x`）与 `CURRENT.md` 的残余风险；未知格式透传时不得宣称“已完全脱敏”。
- 测试：`_AC_XX` 命名、独立测试库、无静默 skip、反向验证。
- 前端（改动涉及 `apps/` 时）：按[前端规范](frontend.md)核对——新增组件/hook 是否先查重、新依赖是否声明、`lib/api-types.ts` 是否被手改、`"use client"` 是否只在最小叶子、是否新增颜色字面量或非标间距、错误/空/加载三态与 a11y 是否覆盖、测试是否被弱化。
- 坏味道只作 judgement call，不替代已文档化标准。

## Spec 轴

- 逐条对照 brief 的 AC、plan 的对应章节、features 的 `Description/Steps`。
- 读模型/摘要/列表接口：字段来源、缺省与截断、租户/权限是否在 plan 的「只读投影」表定义并有 AC 覆盖。
- 区分「缺失」与「已批准到后续 feature」；引用规格原文行。
- 检查 scope creep：新表/新接口/新配置是否在 plan 或执行卡声明。
- 检查证据：测试数、`Passes`、执行卡第 4 节、`CURRENT.md` 三处一致。

## 输出

- 每条 finding 标「阻塞 / 建议 / 接受为后续」。
- `## 逐 AC` 每行必须有可复查证据。
- `## 阻断项` 写「无」或编号 + 位置 + 必须修复项。
- 结论只用：通过 / 有条件通过 / 不通过。
