# M1 澄清清单

- 状态：已清零（2026-11-14）
- 日期：2026-11-14
- 用途：把 M1 规格里“未写明、实现时必须决定”的事项集中列出。每条给出选项与建议默认值；答复后写回对应规格或 ADR，本条目才关闭。
- 规则：本清单存在未关闭条目时，相关任务保持“未就绪”；答复不得只留在对话中。

## 环境类

### C-01 本地数据库版本与运行方式

- 状态：已关闭
- 答复（2026-11-14）：采用 PostgreSQL 17.12，Homebrew 安装并以 `brew services start postgresql@17` 运行；`localhost:5432`，超级用户为 `ba`，不引入 Docker。已卸载并删除 PostgreSQL 14 及其数据目录。
- 验证：`pg_isready` 返回接受连接；`select version()` 返回 `PostgreSQL 17.12 (Homebrew)`。
- 影响：ADR-0004、T-01 完成标准（已同步移除 `docker-compose.yml`）。

### C-02 数据库迁移与种子数据方式

- 状态：已关闭
- 答复：采用 Alembic 管理迁移，种子数据由独立脚本提供。
- 已写回：`docs/adr/0004-engineering-baseline.md` 编码与检查规范。
- 影响：T-01、T-06。

## 身份与租户类

### C-03 认证方式

- 状态：已关闭
- 答复：开发期使用固定测试账号与简单会话 Cookie，不做注册登录。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` 身份与租户一节。
- 影响：FR-01、T-04、AC-02、AC-03。

### C-04 租户模型

- 状态：已关闭
- 答复：固定两个租户，各带两个用户；跨租户用例使用真实存在的第二租户数据。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` 身份与租户一节。
- 影响：AC-03、AC-15、T-04。

## 数据夹具类

### C-05 Mock OMS 预置订单

- 状态：已关闭
- 答复：每租户 4 单，分别覆盖 `PAID_UNFULFILLED`、`FULFILLING`、`SHIPPED`、`CANCELLED`；另加 1 单属于同租户其他用户，用于越权用例。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` Mock OMS 一节。
- 影响：AC-01、AC-02、AC-07。

## 时间参数类

### C-06 确认超时时长

- 状态：已关闭
- 答复：默认 30 分钟，可由环境变量覆盖；测试中设置为 1 秒。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` Workflow 与幂等一节。
- 影响：AC-19。

### C-07 重试次数与间隔

- 状态：已关闭
- 答复：最多 3 次，指数退避 1s / 2s / 4s；耗尽后进入 `MANUAL_REVIEW`。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` Workflow 与幂等一节。
- 影响：AC-12。

### C-08 外部调用超时阈值

- 状态：已关闭
- 答复：单次 OMS 调用 2 秒超时；Mock OMS 可注入高于该值的延迟以触发 `SUBMIT_UNKNOWN`。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` Workflow 与幂等一节。
- 影响：AC-10、AC-11。

## 模型与可观测类

### C-09 模型供应商与结构化输出

- 状态：已关闭
- 答复：定义可替换的模型调用接口，M1 只实现一个供应商；具体供应商在 T-09 的任务设计卡中选定。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` 第 10 节。
- 影响：T-09。

### C-10 Trace 存储与导出

- 状态：已关闭
- 答复：M1 只要求 `trace_id` 贯穿结构化日志；导出后端推迟到 T-12 决定。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` 第 10 节。
- 影响：AC-17。

### C-11 审计脱敏字段清单

- 状态：已关闭
- 答复：禁止记录令牌、密码、完整卡号、完整手机号、完整地址；允许记录订单号、用户 ID、状态、错误码。
- 已写回：`docs/specs/M1/001-order-cancel/design.md` 可观测性一节。
- 影响：AC-18、T-12。

## 交互类

### C-12 刷新后的会话恢复范围

- 状态：已关闭
- 答复：恢复最近任务状态与消息列表，不重开会话。
- 已写回：`docs/specs/M1/001-order-cancel/ui.md` 确认交互规则。
- 影响：AC-04、AC-05、T-10。
