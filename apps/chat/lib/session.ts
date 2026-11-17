export type Customer = {
  id: string;
  tenant_id: string;
  username: string;
  display_name: string;
};

export type Conversation = {
  id: string;
  status: string;
  after_id: number;
};

export type Session = {
  customer: Customer;
  conversation: Conversation;
  expires_at: string;
};

export type MessageAuthor = "customer" | "ai" | "agent" | "system";

export type Message = {
  id: number;
  author_type: MessageAuthor;
  content: string;
  created_at: string;
};

// POST /customer/messages 与 GET /customer/messages 共用同一响应形状。
export type MessagePage = {
  conversation_id: string;
  status: string;
  after_id: number;
  messages: Message[];
};

type ErrorBody = {
  code?: unknown;
  message?: unknown;
  detail?: unknown;
};

const FALLBACK_ERROR = "请求失败，请稍后再试";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function readError(response: Response): Promise<ApiError> {
  let body: ErrorBody = {};
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    // 非 JSON 响应沿用兜底文案。
  }
  // 契约：优先 message，其次 detail；两者都兼容非字符串的兜底响应。
  const message =
    (typeof body.message === "string" && body.message.trim()) ||
    (typeof body.detail === "string" && body.detail.trim()) ||
    FALLBACK_ERROR;
  const code = typeof body.code === "string" ? body.code : undefined;
  return new ApiError(message, response.status, code);
}

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
  const response = await fetch("/api/customer/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
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

export async function getMessages(afterId: number): Promise<MessagePage> {
  const response = await fetch(`/api/customer/messages?after_id=${encodeURIComponent(afterId)}`);
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as MessagePage;
}

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function sendMessage(
  content: string,
  idempotencyKey: string = newIdempotencyKey(),
): Promise<MessagePage> {
  const response = await fetch("/api/customer/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as MessagePage;
}
