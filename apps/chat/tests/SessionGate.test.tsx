import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionGate } from "@/components/SessionGate";

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
  conversation: { id: "conv-1", status: "AI_ACTIVE", after_id: 0 },
  expires_at: "2026-11-18T03:00:00Z",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("SessionGate", () => {
  beforeEach(() => {
    replace.mockReset();
    requestedConversationId = null;
    vi.restoreAllMocks();
  });

  it("未登录时跳转 /login", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID", message: "未登录" }, 401));
    render(<SessionGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/session");
  });

  it("已登录时展示客户、会话状态和占位，退出后跳转 /login", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<SessionGate />);
    expect(await screen.findByText("客户甲")).toBeInTheDocument();
    expect(screen.getByText("conv-1")).toBeInTheDocument();
    expect(screen.getByText("AI_ACTIVE")).toBeInTheDocument();
    expect(screen.getByText("消息功能下一刀接入")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenLastCalledWith("/api/customer/sessions", { method: "DELETE" });
  });

  it("URL 指定的会话不存在时提示并允许返回", async () => {
    requestedConversationId = "conv-other";
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "NOT_FOUND", message: "会话不存在" }, 404));
    render(<SessionGate />);
    expect(await screen.findByText("会话不存在")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/customer/conversations/conv-other");

    fireEvent.click(screen.getByRole("button", { name: "返回" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat"));
  });

  it("URL 指定会话时展示服务端返回的会话", async () => {
    requestedConversationId = "conv-2";
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(
        json({
          customer: session.customer,
          conversation: { id: "conv-2", status: "QUEUED", after_id: 0 },
          expires_at: session.expires_at,
        }),
      );
    render(<SessionGate />);
    expect(await screen.findByText("conv-2")).toBeInTheDocument();
    expect(screen.getByText("QUEUED")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/customer/conversations/conv-2");
  });

  it("网络错误时显示可重试提示", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(json(session));
    render(<SessionGate />);
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成，请重试");
    expect(replace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("客户甲")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("退出失败时提示且可重试", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "INTERNAL", message: "服务不可用" }, 500))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<SessionGate />);
    fireEvent.click(await screen.findByRole("button", { name: "退出" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("退出失败，请重试");
    expect(replace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/customer/sessions", { method: "DELETE" });
  });
});
