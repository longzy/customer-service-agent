# 评审记录：F-XX <任务名>

- 日期：YYYY-MM-DD
- 评审者：独立上下文（未参与实现），共 N 轮；Standards 轴与 Spec 轴并行
- 评审范围：`git diff <fixed>...<head>`（`<fixed>` 为本 feature 开工前 HEAD，即首个 feature 提交的父提交；可用 `git rev-parse <first-commit>^`）
- 评审输入：`python3 scripts/review_pack.py F-XX` 生成的评审包
- 依据：执行卡、`plan.md` 第 X 节、AC-XX

## 0. 门禁复核

先跑 `make verify-check`；红则直接「不通过」，不做深度评审。机械前置用 `make review-check`（快，不是全量门禁）。

| 门禁 | 结果 |
|---|---|
| `make verify-check` | |
| `make review-check` | |
| AC 定向测试（独立 `TEST_DB_NAME`） | |
| `./scripts/check-contracts.sh` | |

## Standards 轴报告

（评审者原文；0 阻断 / N 条建议；只报文档化标准与 judgement call）

## Spec 轴报告

（评审者原文；缺失/部分/越界/实现方式不符；已批准到后续 feature 的要标明）

## 逐 AC

| AC | 判定点 | 结论 | 证据（测试名/命令/文件行号） |
|---|---|---|---|
| AC-XX | | 通过 / 未完成 | |

## 阻断项

无；或有：编号 + 位置 + 必须修复项。非阻塞项标「建议 / 接受为后续」并写承接 feature。

## 结论

通过 / 有条件通过 / 不通过。N 轮：…（一句话说明阻断项是否关闭）。
