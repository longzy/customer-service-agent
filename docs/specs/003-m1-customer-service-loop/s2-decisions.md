# M1 S2 前置决策（1 页）

- 状态：草案
- 日期：2026-11-16
- 目的：先定数据所有权、actor、legacy/快照、范围和保留；这些不定，不写完整设计。
- 依据：[requirements](requirements.md)、[design](design.md)、[ADR-0006](../../adr/0006-customer-login.md)

## 决策

| # | 决策 | 结果 |
|---|---|---|
| 1 | 数据所有权 | M1 新建 `service_*` 表；M1-P 旧表/旧路由/旧测试原样保留；一个客户一个未关闭会话用部分唯一索引；同一会话一张 open 交接单用部分唯一索引；不做 `order_access_grants` |
| 2 | Actor/ToolContext | `Actor(customer_id/employee_id)` + `ToolContext(actor, oms_access, trace_id, journey_id)`；客户 `OmsAccess(tenant, user_id=customer.oms_user_id)`；坐席用交接单 `verified_order_ids`；取消 actor 在 006 |
| 3 | Legacy/快照 | 旧表/旧路由不动；AC-27/28 改为子集兼容（旧路径/表不变，新 M1 允许）；另加 `openapi-m1.json`/`db-schema-m1.json` 全量快照；`M1_ENABLED` 控制新路由/worker |
| 4 | 范围/演示 | 003 验收+契约；004 客户聊天；005 坐席工作台；006 取消最后；2 客户+2 坐席，A 全链路/B 隔离 |
| 5 | 会话 | 客户登录 24h 绝对 session；一个客户一个未关闭会话，登录恢复；员工 8h；`AI_ACTIVE` 空闲 24h 关闭，`QUEUED/HUMAN_ACTIVE` 不自动关闭 |
| 6 | 保留/审计 | 会话 24h；消息/交接单终态后 30d；审计 90d；不存完整手机号；审计写失败变更 503 不提交；客户账号停用保留审计 |

## 首版 S2 阻断项闭合

| B | 决策如何闭合 |
|---|---|
| B-01 唯一约束/可空 user_id | 新 `service_*` 表；旧表不动；一个 open 会话/一张 open 交接单用部分唯一索引 |
| B-02 旧 M1-P/快照 | 旧路由/测试不动；AC-27/28 子集兼容 + M1 全量快照；`M1_ENABLED` |
| B-03 匿名/坐席取消 | 客户账号 actor；006 定义 `customer_id`/`requested_by`/`confirmed_by`；坐席不能代确认 |
| B-04 队列租户/并发 | 003 契约：租户条件、版本、404/409、handoff+conversation+audit/outbox 同事务 |
| B-05 状态机 | 003 第 4 节：QUEUED 客户关闭、转回 AI 终态旧单、排队消息、重复交接 |
| B-06 客户 API | 003 第 10 节：登录、订单列表/详情、按会话读取；无订单校验接口 |
| B-07 模块/事务 | 003 第 2/7 节：`agent_runtime`、R7、审计模块、事务归属表 |
| B-08 Trace/ToolContext | `journey_id`/`trace_id` 进 ToolContext；`service_model_events`/`service_tool_events`/`service_audit_events` |
| B-09 保留/worker | 终态后 30d；open 单不删；账号停用语义；worker 可注入时钟 |
| B-10 登录/限速 | scrypt、24h/8h、轮换、非枚举、PG 桶、可信 IP、429 先行 |
| B-11 威胁/回滚 | 003 第 13 节含登录爆破/清理遗漏/内部滥用；回滚目标上一 release；`M1_ENABLED` |
| B-12 CI/评测 | `verify.sh` 加 chat/workspace；`evals/run.py` 支持 AC-30~49；快照重基线 |

## 未决项

- 决策层无未决；UI 文案、模型成本、密码策略、审计归档介质在 004/005/006 S2 关闭。
- 详细 API/DDL/状态图在 003 design；本页只做“先定方向”。
