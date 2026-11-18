import { readError } from "@/lib/api-client";

import type { ClaimResult, QueueItem, QueueResponse } from "../types";

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

/**
 * 条件领取；成功返回会话 id 供跳转。
 * 409/404 抛 ApiError（携带 code），由调用方提示并刷新队列；401/403 返回 null。
 */
export async function claimHandoff(handoffId: string): Promise<ClaimResult | null> {
  const response = await fetch(`/api/workspace/queue/${encodeURIComponent(handoffId)}/claim`, {
    method: "POST",
  });
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as ClaimResult;
}
