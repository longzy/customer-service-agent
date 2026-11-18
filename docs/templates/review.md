# 评审记录：F-XX <任务名>

- 日期：YYYY-MM-DD
- 评审者：独立上下文（未参与实现），共 N 轮
- 评审范围：`git diff <fixed>...HEAD`（<fixed> 为本 feature 开工前 HEAD，即首个实现提交的父提交；可用 `git rev-parse <first-feat-commit>^`）
- 依据：执行卡、`plan.md` 第 X 节、AC-XX

## 0. 门禁复核

先跑 `make verify-check`；红则直接「不通过」，不做深度评审。

## 结论

通过 / 有条件通过 / 不通过。N 轮：…（一句话说明阻断项是否关闭）。

## 逐 AC

| AC | 结论 | 证据 |
|---|---|---|
| AC-XX | 通过 / 未完成 | 文件:行号或命令 |

## 阻断项

无；或有：编号 + 位置 + 必须修复项。
