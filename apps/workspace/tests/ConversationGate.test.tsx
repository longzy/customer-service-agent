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

const detail = {
  id: "conv-1",
  status: "CLAIMED",
  customer: { username: "customer_a", display_name: "客户甲" },
  handoff: {
    id: "ho-1",
    status: "CLAIMED",
    reason: "CUSTOMER_REQUEST",
    summary: "客户甲要求转人工",
    pending_step: "等待坐席接入",
    order_count: 0,
    messages: [
      {
        id: 1,
        author_type: "customer",
        content: "转人工",
        created_at: "2026-11-17T10:00:00Z",
      },
    ],
    ai_trace: [
      {
        event_type: "intent",
        name: "handoff_keyword",
        status: "matched",
        confidence: null,
        created_at: "2026-11-17T10:00:00Z",
      },
    ],
  },
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

  it("显示领取者可见的客户与交接单上下文", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json(detail));
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("conv-1")).toBeInTheDocument();
    expect(screen.getByText("客户甲")).toBeInTheDocument();
    expect(screen.getByText(/customer_a/)).toBeInTheDocument();
    expect(screen.getByText("已领取，等待接管")).toBeInTheDocument();
    expect(screen.getByText("客户甲要求转人工")).toBeInTheDocument();
    expect(
      screen.getAllByText((content) => content.includes("客户要求转人工")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("等待坐席接入")).toBeInTheDocument();
    expect(screen.getByText("转人工")).toBeInTheDocument();
    expect(screen.getByText("intent · handoff_keyword")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接管会话" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← 待接入队列" })).toHaveAttribute("href", "/queue");
  });

  it("会话不存在时提示未找到且不暴露细节", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "NOT_FOUND", message: "未找到" }, 404));
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("未找到该会话")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回队列" })).toBeInTheDocument();
  });

  it("AC-36 接管成功后会话语义变为人工接入中", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json(detail))
      .mockResolvedValueOnce(json({ conversation_id: "conv-1", status: "HUMAN_ACTIVE" }));
    render(<ConversationGate conversationId="conv-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "接管会话" }));

    expect(await screen.findByText("已接管会话，客户将看到“人工已接入”。")).toBeInTheDocument();
    expect(screen.getByText("人工接入中")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "接管会话" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/workspace/conversations/conv-1/takeover", {
      method: "POST",
    });
  });

  it("AC-36 接管返回 404 时提示状态已变化", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json(detail))
      .mockResolvedValueOnce(json({ code: "NOT_FOUND", message: "未找到" }, 404));
    render(<ConversationGate conversationId="conv-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "接管会话" }));

    expect(await screen.findByText("会话状态已变化，请刷新后重试。")).toBeInTheDocument();
    expect(screen.getByText("已领取，等待接管")).toBeInTheDocument();
  });

  it("退出后回登录页", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json(detail))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("conv-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
