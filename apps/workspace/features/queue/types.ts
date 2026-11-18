import type { components } from "@/lib/api-types";

// 队列契约来自 FastAPI OpenAPI 生成类型；不要手写响应字段。
export type QueueItem = components["schemas"]["WorkspaceQueueItem"];
export type QueueResponse = components["schemas"]["WorkspaceQueueResponse"];
export type ClaimResult = components["schemas"]["WorkspaceClaimResponse"];
