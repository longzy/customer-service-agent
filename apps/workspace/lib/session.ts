import type { components } from "./api-types";

// 统一从 FastAPI OpenAPI 生成；不要在本文件手写响应字段。
export type Employee = components["schemas"]["EmployeePublic"];
export type Session = components["schemas"]["EmployeeSessionResponse"];
type EmployeeLoginRequest = components["schemas"]["EmployeeLoginRequest"];

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

export async function readError(response: Response): Promise<ApiError> {
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
  const response = await fetch("/api/workspace/session");
  // 401 未登录；403 角色已不是坐席：两者都回登录页，不把工作台暴露给非 agent。
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as Session;
}

export async function login(username: string, password: string): Promise<Session> {
  const body: EmployeeLoginRequest = { username, password };
  const response = await fetch("/api/workspace/sessions", {
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
  const response = await fetch("/api/workspace/sessions", { method: "DELETE" });
  // 会话已失效等同于退出成功，避免把坐席困在工作台。
  if (!response.ok && response.status !== 401) {
    throw await readError(response);
  }
}
