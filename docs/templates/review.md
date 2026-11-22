# 评审记录：F-XX <任务名>

- 日期：YYYY-MM-DD
- 评审者：独立上下文（未参与实现），共 N 轮；Standards 轴与 Spec 轴并行
- 评审范围：`git diff <fixed>...<head>`（`<fixed>` 为本 feature 开工前 HEAD，即首个 feature 提交的父提交；可用 `git rev-parse <first-commit>^`）
- 评审输入：`python3 scripts/review_pack.py F-XX` 生成的评审包
- 依据：执行卡、`design.md` 第 X 节、AC-XX

## 0. 门禁复核

先跑 `make review-check` 与绑定 AC 定向测试；红则直接「不通过」，不做深度评审。全量由收口回填，收口全量失败则评审作废。

| 门禁 | 结果 |
|---|---|
| `make verify-changed` + 定向 AC | |
| 收口全量（回填） | |
| `make review-check` | |
| AC 定向测试（独立 `TEST_DB_NAME`） | |
| `./scripts/check-contracts.sh` | |

## Standards 轴报告

（评审者原文粘贴，不摘要；0 阻断 / N 条建议；只报文档化标准与 judgement call）

## Spec 轴报告

（评审者原文粘贴，不摘要；缺失/部分/越界/实现方式不符；已批准到后续 feature 的要标明）

## 安全评审（T3）

> T3 必填，由未参与实现的独立安全评审者填写；结论只写 通过 / 有条件通过 / 不通过。
> 非 T3 可写“不适用”。

- 评审者：
- 威胁模型与越权矩阵：
- 认证 / 租户 / 归属：
- 幂等、重放与并发：
- PII、日志与审计：
- 回滚、监控与依赖/供应链：
- 结论：通过

## 逐 AC

| AC | 判定点 | 结论 | 证据（测试名/命令/文件行号） |
|---|---|---|---|
| AC-XX | | 通过 / 未完成 | |

## 阻断项

无；或有：编号 + 位置 + 必须修复项。非阻塞项标「建议 / 接受为后续」并写承接 feature。

## 结论

通过。N 轮：…（一句话说明阻断项是否关闭）。

> 结果不是通过时把首词换成「有条件通过」或「不通过」；首行不要加粗，检查器按首行判定。
