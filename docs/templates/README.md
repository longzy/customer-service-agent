# 文档模板

- 模板版本：2026-11-21
- 适用：所有 `docs/specs/<NNN>-<slug>/` 与执行卡
- 原则：**模板先行**。模板是 schema，文档是 instance；先定模板，再生成/评审文档。没有模板基线，不批准 spec。

## 1. 顺序

```text
模板基线（本目录 + WORKFLOW §8）
  -> requirements.md（Frame）
  -> design.md（Plan）
  -> tasks.md / 执行卡（Build）
```

模板变更先于文档变更；模板定稿后，进行中的 spec 要按新模板复核，不反向让模板迁就单篇文档。

## 2. 模板索引

| 文件 | 阶段 | 产物 | 必须包含 | 不该包含 |
|---|---|---|---|---|
| [requirements.md](requirements.md) | Frame | `docs/specs/<spec>/requirements.md` | PR/FAQ、范围/非目标、成功度量、AC、切片；可选产品决策/用户故事/判定表 | 表名、API、索引、事务、工具名、任务编号 |
| [design.md](design.md) | Plan | `docs/specs/<spec>/design.md` | Context/Goals/Design/Alternatives/Cross-cutting/未决；数据与一致性、事务边界、失败路径、备选与 Drawbacks、威胁模型、seam、回滚 | 重复产品目标；完整 OpenAPI/schema |
| [task-design-card.md](task-design-card.md) | Build | `docs/tasks/<spec>/F-XX.md` | DoR、seam、判定表、验证、证据、评审、DoD；T2/T3 发布/回滚 | 重复 design 的完整方案 |

## 3. 质量门槛

- requirements：AC 用客户/坐席可观察语言；复杂 AC 有判定表；范围与非目标明确。
- design：至少 1 个真实备选；写清 Drawbacks；数据/API/状态机/并发/事务/失败路径可执行；未决问题清零。
- 执行卡：DoR 全部满足才开工；判定表每格有测试或豁免；证据只写命令/测试名/结论；DoD 全部勾选才 done。
- 模板不替代评审：模板保证结构，评审判断内容与取舍。

## 4. 变更控制

模板变更必须：

1. 更新本目录对应文件与 `模板版本` 日期；
2. 更新 [WORKFLOW](../process/WORKFLOW.md) §8；
3. 复核进行中的 spec 是否仍符合模板；
4. 不批量重写已完成执行卡；新卡按新模板。
