import { readError } from "@/lib/api-client";

import type { ConversationDetail } from "../types";

/**
 * 已领取会话的最小读取；401/403 返回 null，由页面统一回登录页。
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
