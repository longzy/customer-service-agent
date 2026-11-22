import { readError } from "@/lib/api-client";

import type { CancellationTask } from "../types";

// 取消写接口只接受订单号；身份与会话由 HttpOnly Cookie 提供。
const BASE = "/api/customer/cancellations";

async function readTask(response: Response): Promise<CancellationTask> {
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as CancellationTask;
}

export async function createCancellation(orderId: string): Promise<CancellationTask> {
  const response = await fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order_id: orderId }),
  });
  return readTask(response);
}

export async function confirmCancellation(taskId: string): Promise<CancellationTask> {
  const response = await fetch(`${BASE}/${encodeURIComponent(taskId)}/confirm`, {
    method: "POST",
  });
  return readTask(response);
}

export async function declineCancellation(taskId: string): Promise<CancellationTask> {
  const response = await fetch(`${BASE}/${encodeURIComponent(taskId)}/decline`, {
    method: "POST",
  });
  return readTask(response);
}

export async function refreshCancellation(taskId: string): Promise<CancellationTask> {
  const response = await fetch(`${BASE}/${encodeURIComponent(taskId)}/refresh`, {
    method: "POST",
  });
  return readTask(response);
}
