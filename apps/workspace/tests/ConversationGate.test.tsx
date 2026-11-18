import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConversationGate } from "@/features/conversation";

const replace = vi.fn();
const router = { replace, push: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

const session = {
  employee: {
    id: "emp-agent_1",
    tenant_id: "tenant-a",
    username: "agent_1",
    display_name: "坐席 1",
    role: "agent",
  },
  expires_at: "2026-11-17T11:00:00Z",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("工作台 ConversationGate", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("未登录时跳转 /login", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({ code: "SESSION_INVALID", message: "未登录" }, 401),
    );
    render(<ConversationGate conversationId="conv-1" />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("显示已领取会话编号与状态", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ id: "conv-1", status: "CLAIMED" }));
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("conv-1")).toBeInTheDocument();
    expect(screen.getByText("已领取，等待接管")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回队列" })).toHaveAttribute("href", "/queue");
  });

  it("会话不存在时提示未找到且不暴露细节", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "NOT_FOUND", message: "未找到" }, 404));
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText(/未找到该会话/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回队列" })).toBeInTheDocument();
  });

  it("退出后回登录页", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ id: "conv-1", status: "CLAIMED" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("conv-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
