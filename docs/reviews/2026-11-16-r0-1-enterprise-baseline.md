# R0-1 企业化产品重基线评审

- 日期：2026-11-16
- 范围：产品宪章、路线图、ADR-0005、总体架构、架构不变量、术语与入口
- 评审人：用户（产品/业务负责人）
- 实现：AI Agent（lead）
- 结论：通过

## 1. 送审内容

| 文件 | 变更 |
|---|---|
| [`docs/product/charter.md`](../product/charter.md) | 重写为企业内部 AI 客服定位；角色、M1 范围、Mock 边界、指标与假设 |
| [`docs/roadmap.md`](../roadmap.md) | 重写为 M0 → M1-P → R0 → 企业 M1 → M2–M5 |
| [`docs/adr/0005-enterprise-boundary.md`](../adr/0005-enterprise-boundary.md) | 新增产品/角色/身份/Mock/模块/验收边界与不变量影响 |
| [`docs/architecture/overview.md`](../architecture/overview.md) | 两个前端、匿名会话、队列/接管、OmsPort 与依赖规则 |
| [`docs/architecture/invariants.md`](../architecture/invariants.md) | 修订 INV-01/02/03/11，新增 INV-17/18/19 |
| [`docs/GLOSSARY.md`](../GLOSSARY.md)、`README.md`、`CLAUDE.md`、`GEMINI.md` | 术语、入口与链接对齐 |
| [`docs/CURRENT.md`](../CURRENT.md)、[`docs/initiatives/2026-11-16-enterprise-reset.md`](../initiatives/2026-11-16-enterprise-reset.md) | 状态与决策日志更新 |

## 2. 用户确认的决策

- 客户在 M1 保持匿名，不建客户账号。
- M1 员工角色只有 `agent`；`supervisor`/`admin` 到 M4。
- 匿名客户查单/取消用订单号 + 下单手机号后四位校验，M1 不接短信。
- 只有 OMS（及 M2 后的支付/物流）允许 Mock；身份、会话、队列、工作台、审计必须真实。
- 客户聊天与坐席工作台是两个前端。

## 3. 检查证据

```text
$ python3 scripts/check-docs.py
文档检查通过：81 个文件、53 条链接、1 个规格目录、21 条 AC、0 张执行卡已检查、21 张跳过、21 份评审记录已核对。

$ python3 scripts/check-status.py
状态一致性检查通过：21 个已完成任务、0 个未完成任务、21 张执行卡与 CURRENT.md 对齐。

$ python3 scripts/trace.py --strict
追溯检查通过：21 条 AC，0 条已登记基线。
```

完整门禁 `./scripts/verify.sh` 结果见本文第 6 节与 `docs/CURRENT.md` 的验证块。

## 4. 不变量变更

| 不变量 | 变更 |
|---|---|
| INV-01 | 调用主体标识从“用户”放宽为“匿名会话或员工用户” |
| INV-02 | 区分员工认证上下文与匿名客户会话 |
| INV-03 | 订单授权改为客户订单号 + 手机尾号校验，或坐席接管/队列授权 |
| INV-11 | 转人工必须有队列、领取与关闭闭环，不得是死路 |
| INV-17 | 工作台接口必须服务端校验角色与会话归属 |
| INV-18 | 领取与接管必须防重复和并发冲突 |
| INV-19 | 只有外部业务系统允许 Mock，生产缺 OMS 配置启动失败 |

ADR 依据：[ADR-0005](../adr/0005-enterprise-boundary.md)。实现者未参与批准，批准人为用户。

## 5. 遗留与承接

- R0-2：后端模块边界、`check-imports.py`、`platform`/`identity`/`adapters` 骨架（下一步）。
- 新 M1 规格与任务地图：登录/RBAC、匿名会话、订单校验、AI 回复、转人工队列、工作台、审计。
- 待 M1 规格确定：队列分配策略、匿名会话与订单校验记录保留期。
- 分支保护仍受 GitHub 套餐限制，不阻塞 R0-2。

## 6. 完整门禁

```text
$ ./scripts/verify.sh
...
== pytest（独立测试库）==
413 passed
== 追溯矩阵 ==
追溯检查通过：21 条 AC，0 条已登记基线
== docs ==
文档检查通过
== web test ==
Test Files  5 passed (5)
Tests  40 passed (40)
- 最近验证：`./scripts/verify.sh` 全部检查通过——pytest 413 passed（独立测试库）、
  mypy 39 个文件、追溯矩阵通过（21 条 AC）、文档与前端检查通过
```

退出码 0。`docs/CURRENT.md` 的验证块由 `verify.sh` 自动回写。

## 结论

通过（2026-11-16，用户批准）。R0-1 关闭，进入 R0-2。
