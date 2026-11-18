import type { components } from "./api-types";

import { readError } from "./api-client";

// 统一从 FastAPI OpenAPI 生成；不要在本文件手写响应字段。
export type Employee = components["schemas"]["EmployeePublic"];
export type Session = components["schemas"]["EmployeeSessionResponse"];
type EmployeeLoginRequest = components["schemas"]["EmployeeLoginRequest"];

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
