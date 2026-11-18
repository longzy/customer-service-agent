# packages/contracts

跨模块接口的唯一定义来源。

## 文件

- `schemas/domain.json`：M1 领域契约（OrderSummary/OrderDetail/OrderItem/CancelEligibility、订单/取消/错误码枚举）。Python 类型在 `backend/domain/`，由契约测试保证对齐。
- `openapi.json`：`scripts/export_openapi.py` 从 FastAPI production 形态导出的完整 OpenAPI；test-only 路由不进入。
- `package.json`：持有 `openapi-typescript`，只负责生成前端类型。

## 前端类型

```bash
# 改了后端请求/响应/错误封套后
pnpm -C packages/contracts generate     # 生成 apps/chat 与 apps/workspace 的类型
./scripts/check-api-types.sh            # 校验 OpenAPI 快照 + 生成物是否最新
```

- `apps/chat/lib/session.ts`、`apps/workspace/lib/session.ts` 只做 `components["schemas"][...]` 别名；**不手写响应字段**。
- `apps/chat/lib/api-types.ts`、`apps/workspace/lib/api-types.ts` 是生成物，不手改，不进入 Prettier。
- 金额统一整数分；时间为带 `Z` 的 ISO 8601 UTC 字符串；未知字段一律拒绝。
- 完整决策见 [ADR-0007](../../docs/adr/0007-openapi-frontend-types.md)。
