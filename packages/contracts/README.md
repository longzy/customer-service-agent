# packages/contracts

跨模块接口的唯一定义来源。

- `schemas/domain.json`：M1 领域契约，包含 OrderSummary、OrderDetail、OrderItem、CancelEligibility 与三个枚举（订单状态、取消状态、错误码）。
- 金额统一为整数分；时间为带 `Z` 的 ISO 8601 UTC 字符串；未知字段一律拒绝。
- Python 类型位于 `backend/domain/`，由契约测试保证与 Schema 对齐。
- OpenAPI 由后端自动生成，T-03 落地后导出到本目录；前端类型由 OpenAPI 生成，不手写。
