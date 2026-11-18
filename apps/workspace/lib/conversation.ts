import type { components } from "./api-types";

import { readError } from "./session";

// 会话入口契约来自 FastAPI OpenAPI 生成类型；不要手写响应字段。
export type ConversationDetail = components["schemas"]["WorkspaceConversationResponse"];

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
