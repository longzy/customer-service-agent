# ADR-0007：OpenAPI 作为新前端的类型事实源

- 状态：已批准
- 日期：2026-11-17
- 批准：2026-11-17（用户要求使用 OpenAPI，并一起修复手写类型漂移）
- 关联：[总体架构](../architecture/overview.md)、[工程标准](../process/standards.md)、[contracts/README](../../packages/contracts/README.md)

## 上下文

`packages/contracts/README` 原先声称“前端类型由 OpenAPI 生成”，但实际：

- 没有导出、生成、校验三条命令；
- 新客户 API 的响应是 `dict[str, Any]`，OpenAPI 里是 `additionalProperties: true`，即使生成也只能得到 `Record<string, unknown>`；
- `apps/chat` 手写响应类型，无法与后端字段/枚举保持一致；
- 没有检查器阻止“手写类型与契约漂移”。

## 决策

1. **FastAPI OpenAPI 是唯一类型事实源**。`scripts/export_openapi.py` 用 production 形态的 app 导出 `packages/contracts/openapi.json`；test-only 路由不进入契约。
2. **响应必须有模型**。客户 API 使用 `backend/api/customer_schemas.py` 的 Pydantic 响应模型；OpenAPI 不得再出现 `additionalProperties: true` 的业务响应。
3. **生成而非手写**。`packages/contracts` 持有 `openapi-typescript`，生成 `apps/chat/lib/api-types.ts`；前端 `lib/session.ts` 只做类型别名，不手写字段。
4. **漂移可自动发现**。`scripts/check-api-types.sh` 同时校验 OpenAPI 快照与生成类型；接入 `verify.sh`；pre-commit 校验 OpenAPI 快照。
5. **M1-P 例外**。`apps/web` 为归档原型，契约不含 test-only `/accounts`，保持手写类型；不把例外扩散到新 M1 前端。

## 备选与不选原因

| 备选 | 不选原因 |
|---|---|
| 继续手写共享类型 | 已经发生漂移；评审只能靠人眼，无法阻止下一次 |
| 从 `domain.json` 生成前端类型 | 只覆盖领域对象，不覆盖 HTTP 请求/响应/错误封套；客户 API 的会话与消息不在 domain.json |
| 在 CI 里临时 `npx openapi-typescript` | 依赖网络与浮动版本；生成结果不可复现 |
| 一次性导出后手工维护 TS | 不是管线，只是把漂移换了个文件 |

## 后果

- 新增依赖 `openapi-typescript`（仅 `packages/contracts` devDependency）。
- API 响应变更必须同步运行 `pnpm -C packages/contracts generate`；`verify.sh` 会拦截未同步。
- 生成文件较大且不进入 Prettier；所有字段修改都在后端模型，前端不手改生成物。
- `apps/web` 的 M1-P 手写类型保留为已知例外；新 M1 前端不得新增手写 API 响应类型。
