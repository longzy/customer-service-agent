import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionGate } from "@/features/chat";

const replace = vi.fn();
const router = { replace, push: vi.fn() };
let requestedConversationId: string | null = null;
const searchParams = {
  get: (key: string) => (key === "conversation_id" ? requestedConversationId : null),
};

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}));

const session = {
  customer: {
    id: "cust-1",
    tenant_id: "tenant-a",
    username: "customer_a",
    display_name: "客户甲",
  },
  conversation: { id: "conv-1", status: "AI_ACTIVE", after_id: 2 },
  expires_at: "2026-11-18T03:00:00Z",
};

const historyPage = {
  conversation_id: "conv-1",
  status: "AI_ACTIVE",
  after_id: 2,
  messages: [
    {
      id: 2,
      author_type: "ai",
      content: "加载到的历史消息",
      created_at: "2026-11-17T07:00:00Z",
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    return handler(url, init);
  });
}

describe("SessionGate", () => {
  beforeEach(() => {
    replace.mockReset();
    requestedConversationId = null;
    vi.restoreAllMocks();
  });

  it("未登录时跳转 /login", async () => {
    const fetchMock = mockApi((url) => {
      if (url === "/api/customer/session") {
        return json({ code: "SESSION_INVALID", message: "未登录" }, 401);
      }
      throw new Error(`未预期的请求：${url}`);
    });
    render(<SessionGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/session");
  });

  it("AC-42 已登录时展示客户、会话状态与消息，退出后跳转 /login", async () => {
    const fetchMock = mockApi((url, init) => {
      if (url === "/api/customer/session") {
        return json(session);
      }
      if (url === "/api/customer/messages?after_id=0") {
        return json(historyPage);
      }
      if (url === "/api/customer/sessions" && init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      throw new Error(`未预期的请求：${url}`);
    });
    render(<SessionGate />);
    expect(await screen.findByText("客户甲")).toBeInTheDocument();
    expect(screen.getByText("在线支持")).toBeInTheDocument();
    expect(screen.getByText("AI 服务中")).toBeInTheDocument();
    expect(await screen.findByText("加载到的历史消息")).toBeInTheDocument();
    expect(screen.queryByText("消息功能下一刀接入")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/sessions", { method: "DELETE" });
  });

  it("URL 指定的会话不存在时提示并允许返回", async () => {
    requestedConversationId = "conv-other";
    const fetchMock = mockApi((url) => {
      if (url === "/api/customer/session") {
        return json(session);
      }
      if (url === "/api/customer/conversations/conv-other") {
        return json({ code: "NOT_FOUND", message: "会话不存在" }, 404);
      }
      if (url.startsWith("/api/customer/messages")) {
        return json(historyPage);
      }
      throw new Error(`未预期的请求：${url}`);
    });
    render(<SessionGate />);
    expect(await screen.findByText("会话不存在")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/conversations/conv-other");

    fireEvent.click(screen.getByRole("button", { name: "返回" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat"));
  });

  it("AC-42 URL 指定会话时展示服务端返回的会话", async () => {
    requestedConversationId = "conv-2";
    const fetchMock = mockApi((url) => {
      if (url === "/api/customer/session") {
        return json(session);
      }
      if (url === "/api/customer/conversations/conv-2") {
        return json({
          customer: session.customer,
          conversation: { id: "conv-2", status: "QUEUED", after_id: 0 },
          expires_at: session.expires_at,
        });
      }
      if (url.startsWith("/api/customer/messages")) {
        return json({
          conversation_id: "conv-2",
          status: "QUEUED",
          after_id: 0,
          messages: [],
        });
      }
      throw new Error(`未预期的请求：${url}`);
    });
    render(<SessionGate />);
    expect(await screen.findByText("人工接入中")).toBeInTheDocument();
    expect(screen.getByText("正在为你接通人工客服")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/conversations/conv-2");
  });

  it("网络错误时显示可重试提示", async () => {
    let sessionAttempts = 0;
    mockApi((url) => {
      if (url === "/api/customer/session") {
        sessionAttempts += 1;
        if (sessionAttempts === 1) {
          throw new TypeError("Failed to fetch");
        }
        return json(session);
      }
      if (url.startsWith("/api/customer/messages")) {
        return json(historyPage);
      }
      throw new Error(`未预期的请求：${url}`);
    });
    render(<SessionGate />);
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成，请重试");
    expect(replace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("客户甲")).toBeInTheDocument();
    expect(sessionAttempts).toBe(2);
  });

  it("退出失败时提示且可重试", async () => {
    let logoutAttempts = 0;
    const fetchMock = mockApi((url, init) => {
      if (url === "/api/customer/session") {
        return json(session);
      }
      if (url.startsWith("/api/customer/messages")) {
        return json(historyPage);
      }
      if (url === "/api/customer/sessions" && init?.method === "DELETE") {
        logoutAttempts += 1;
        if (logoutAttempts === 1) {
          return json({ code: "INTERNAL", message: "服务不可用" }, 500);
        }
        return new Response(null, { status: 204 });
      }
      throw new Error(`未预期的请求：${url}`);
    });
    render(<SessionGate />);
    fireEvent.click(await screen.findByRole("button", { name: "退出" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("退出失败，请重试");
    expect(replace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(logoutAttempts).toBe(2);
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/sessions", { method: "DELETE" });
  });
});
