import { readError } from "@/lib/api-client";

import type { ConversationDetail, MessagePage, TakeoverResult } from "../types";

/**
 * 已领取会话的完整上下文；401/403 返回 null，由页面统一回登录页。
 * 404（未领取/他人/跨租户）抛 ApiError，由页面提示“未找到”。
 */
export async function getConversation(conversationId: string): Promise<ConversationDetail | null> {
  const response = await fetch(
    `/api/workspace/conversations/${encodeURIComponent(conversationId)}`,
  );
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as ConversationDetail;
}

/**
 * 领取者接管；404（未领取/他人/已接管）与 409（已关闭）抛 ApiError。
 * 401/403 返回 null，由页面统一回登录页。
 */
export async function takeOverConversation(conversationId: string): Promise<TakeoverResult | null> {
  const response = await fetch(
    `/api/workspace/conversations/${encodeURIComponent(conversationId)}/takeover`,
    { method: "POST" },
  );
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as TakeoverResult;
}

/**
 * 会话消息增量轮询；401/403 返回 null（页面回登录页），其余错误抛 ApiError。
 * `afterId` 是服务端上一次返回的 `after_id`，首轮传 0 拉全量历史。
 */
export async function getConversationMessages(
  conversationId: string,
  afterId: number,
): Promise<MessagePage | null> {
  const response = await fetch(
    `/api/workspace/conversations/${encodeURIComponent(conversationId)}/messages?after_id=${encodeURIComponent(afterId)}`,
  );
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as MessagePage;
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** 坐席回复；409（会话已结束）与 422 抛 ApiError，401/403 返回 null。 */
export async function sendConversationReply(
  conversationId: string,
  content: string,
  idempotencyKey: string,
): Promise<MessagePage | null> {
  const response = await fetch(
    `/api/workspace/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({ content }),
    },
  );
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as MessagePage;
}
