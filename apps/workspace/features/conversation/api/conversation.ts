import { readError } from "@/lib/api-client";

import type { ConversationDetail, TakeoverResult } from "../types";

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
