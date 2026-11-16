# 当前项目状态

- 更新日期：2026-11-16
- 项目阶段：M1 订单查询与未发货订单取消（M0 已满足）
- 当前状态：进行中
- 当前 Milestone：M1（规格已批准：`docs/specs/001-order-cancel/`）
- 当前工作：T-11 结果校验（未开工）

<!-- verify:start -->
- 最近验证：`./scripts/verify.sh` 全部检查通过——pytest 318 passed（独立测试库）、mypy 36 个文件、追溯矩阵通过（21 条 AC）、文档与前端检查通过
<!-- verify:end -->

## 进行中

- T-11 结果校验：`services/agent_runtime/validator.py`，承接 AC-16 的回复校验，未建卡。
- T-12 Trace 与审计：请求级 trace_id、审计落盘、日志脱敏，承接 AC-17、AC-18。
- T-13 场景评测：`evals/` 仍是空占位。

## 下一步

1. 为 T-11 出执行卡并先红后绿实现。
2. 完成 T-12，删除 `scripts/trace-baseline.txt` 中两条基线。
3. 完成 T-13：AC-01 至 AC-21 的可重复评测与阈值。
4. 在 GitHub 开启分支保护，把 `verify`、`frontend-build` 设为 required check。

## 已完成

- M0：宪章、架构、不变量、ADR-0001~0004、AI Coding 入口。
- M1：T-01–T-10、T-14–T-20 完成（17/20），含查询、取消、转人工、登录、会话安全基线。
- 门禁：CI + 本地 hook、独立测试库、状态与追溯检查、密钥扫描。
- 流程：单份工作流 + 14 条强制规则，旧流程文档已合并。

## 阻塞

- 无。

## 待确认决策

- 业务：首个入口只用 Web Chat；模拟 OMS 是唯一业务系统。
- 流程：无。

## M1 不做

- 真实订单、支付、物流系统；全渠道；多 Agent 自主协作；完整运营后台。
