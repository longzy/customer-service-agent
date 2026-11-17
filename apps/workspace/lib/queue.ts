import type { components } from "./api-types";

import { readError } from "./session";

// 队列契约来自 FastAPI OpenAPI 生成类型；不要手写响应字段。
export type QueueItem = components["schemas"]["WorkspaceQueueItem"];
export type QueueResponse = components["schemas"]["WorkspaceQueueResponse"];

/**
 * 待接入队列；服务端已按 FIFO 排序，前端不得二次排序。
 * 401/403 返回 null，由页面统一回登录页（与 getSession 语义一致）。
 */
export async function getQueue(): Promise<QueueItem[] | null> {
  const response = await fetch("/api/workspace/queue");
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  const body = (await response.json()) as QueueResponse;
  return body.items;
}
