import type { components } from "@/lib/api-types";

// 列表契约来自 FastAPI OpenAPI 生成类型；不要手写响应字段。
export type CustomerOrderSummary = components["schemas"]["CustomerOrderSummary"];
export type CustomerOrders = components["schemas"]["CustomerOrdersResponse"];
export type CancellationTask = components["schemas"]["CancellationTaskPublic"];
export type CancellationSummary = components["schemas"]["CancellationSummary"];
