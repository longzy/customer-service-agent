# 评审 checklist（F-xx）

- 适用：T2/T3 的独立上下文评审；T1 可裁剪，但门禁复核与逐 AC 结论保留。
- 输出格式：[review 模板](../templates/review.md)。

## 0. 门禁复核

- 先跑 `./scripts/verify.sh --no-record`；失败直接「不通过」。
- 独立跑该 feature 的 `Steps` 命令（AC 定向测试），不只看实现者粘贴的数字。
- 契约变更检查 `./scripts/check-api-types.sh`。

## Standards 轴

- 文档：`standards.md` 的 STD-*、`invariants.md` 的 INV-01/02/03/07/11/12/16/17/18。
- 边界：`overview.md` 的模块依赖与事务提交归属；api 只编排，conversations/identity 不互相越界。
- 安全：身份只来自认证上下文、越权 404、Cookie/密钥/日志脱敏。
- 测试：`_AC_XX` 命名、独立测试库、无静默 skip、反向验证。
- 坏味道只作 judgement call，不替代已文档化标准。

## Spec 轴

- 逐条对照 brief 的 AC、plan 的对应章节、features 的 `Description/Steps`。
- 区分「缺失」与「已批准到后续 feature」；引用规格原文行。
- 检查 scope creep：新表/新接口/新配置是否在 plan 或执行卡声明。
- 检查证据：测试数、`Passes`、执行卡第 4 节、`CURRENT.md` 三处一致。

## 输出

- 每条 finding 标「阻塞 / 建议 / 接受为后续」。
- `## 逐 AC` 每行必须有可复查证据。
- `## 阻断项` 写「无」或编号 + 位置 + 必须修复项。
- 结论只用：通过 / 有条件通过 / 不通过。
