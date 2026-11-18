import type { components } from "./api-types";

import { readError } from "./api-client";

// 统一从 FastAPI OpenAPI 生成；不要在本文件手写响应字段。
export type Customer = components["schemas"]["CustomerPublic"];
export type Conversation = components["schemas"]["ConversationPublic"];
export type Session = components["schemas"]["CustomerSessionResponse"];
type CustomerLoginRequest = components["schemas"]["CustomerLoginRequest"];
type MessagePage = components["schemas"]["MessagePageResponse"];

export async function getSession(): Promise<Session | null> {
  const response = await fetch("/api/customer/session");
  if (response.status === 401) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as Session;
}

export async function login(username: string, password: string): Promise<Session> {
  const body: CustomerLoginRequest = { username, password };
  const response = await fetch("/api/customer/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as Session;
}

export async function logout(): Promise<void> {
  const response = await fetch("/api/customer/sessions", { method: "DELETE" });
  // 会话已失效等同于退出成功，避免把用户困在聊天页。
  if (!response.ok && response.status !== 401) {
    throw await readError(response);
  }
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await fetch(`/api/customer/conversations/${encodeURIComponent(conversationId)}`);
  if (!response.ok) {
    throw await readError(response);
  }
  // 后端契约固定返回 {customer, conversation, expires_at}。
  const body = (await response.json()) as Session;
  return body.conversation;
}

export async function closeSession(idempotencyKey: string): Promise<MessagePage> {
  const response = await fetch("/api/customer/session/close", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as MessagePage;
}
