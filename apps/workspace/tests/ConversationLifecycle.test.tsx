// AC-38 坐席关闭会话与转回 AI 的工作台行为。
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

const humanDetail = {
  id: "conv-1",
  status: "HUMAN_ACTIVE",
  customer: { username: "customer_a", display_name: "客户甲" },
  handoff: {
    id: "ho-1",
    status: "ACTIVE",
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
    ai_trace: [],
  },
};

const claimedDetail = { ...humanDetail, status: "CLAIMED" };

const closedDetail = {
  ...humanDetail,
  status: "CLOSED",
  handoff: { ...humanDetail.handoff, status: "CLOSED" },
};

const messagePage = {
  conversation_id: "conv-1",
  status: "HUMAN_ACTIVE",
  after_id: 4,
  messages: [
    {
      id: 4,
      author_type: "agent",
      content: "您好，我是坐席 1",
      created_at: "2026-11-17T10:05:00Z",
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type RouteHandler = (init?: RequestInit) => Response | Promise<Response>;

function mockRoutes(routes: Record<string, RouteHandler>) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const raw = typeof input === "string" ? input : input.toString();
    const path = raw.split("?")[0];
    const method = (init?.method ?? "GET").toUpperCase();
    const handler = routes[`${method} ${path}`] ?? routes[path];
    if (!handler) {
      return json({ code: "NOT_FOUND", message: "未找到" }, 404);
    }
    return handler(init);
  });
}

function messagesRoute(page: unknown = messagePage) {
  return () => json(page);
}

function baseRoutes(changes: Record<string, RouteHandler> = {}) {
  return {
    "/api/workspace/session": () => json(session),
    "/api/workspace/conversations/conv-1": () => json(humanDetail),
    "/api/workspace/conversations/conv-1/messages": messagesRoute(),
    ...changes,
  };
}

const returnPage = {
  conversation_id: "conv-1",
  status: "AI_ACTIVE",
  after_id: 9,
  messages: [
    {
      id: 9,
      author_type: "system",
      content: "已转回 AI 客服",
      created_at: "2026-11-17T10:06:00Z",
    },
  ],
};

const closePage = {
  conversation_id: "conv-1",
  status: "CLOSED",
  after_id: 10,
  messages: [
    {
      id: 10,
      author_type: "system",
      content: "会话已结束",
      created_at: "2026-11-17T10:06:00Z",
    },
  ],
};

describe("工作台会话关闭与转回 AI", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("AC-38 人工中显示关闭与转回入口并转回 AI", async () => {
    const fetchMock = mockRoutes(
      baseRoutes({
        "POST /api/workspace/conversations/conv-1/return-to-ai": () => json(returnPage),
      }),
    );
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("人工接入中")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关闭会话" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "转回 AI" }));

    expect(await screen.findByText("已转回 AI，客户可继续和 AI 对话。")).toBeInTheDocument();
    expect(screen.getByText("AI 接待中")).toBeInTheDocument();
    // 交接单已随转回终态化：待办快照不再显示为当前任务。
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByLabelText("回复客户")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "关闭会话" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workspace/conversations/conv-1/return-to-ai",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": expect.any(String) }),
      }),
    );

    // 转回后 assignment 已清除：继续轮询只会 404。
    const messagesCalls = () =>
      fetchMock.mock.calls.filter(([input]) => String(input).includes("/messages?after_id="));
    const before = messagesCalls().length;
    await new Promise((resolve) => setTimeout(resolve, 3300));
    expect(messagesCalls().length).toBe(before);
  });

  it("AC-38 点击关闭会话后转为只读", async () => {
    mockRoutes(
      baseRoutes({
        "POST /api/workspace/conversations/conv-1/close": () => json(closePage),
      }),
    );
    render(<ConversationGate conversationId="conv-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "关闭会话" }));

    expect(await screen.findByText("已关闭会话，客户将看到“会话已结束”。")).toBeInTheDocument();
    expect(screen.getByText("已结束")).toBeInTheDocument();
    expect(screen.getByText("会话已结束，仅可查看。")).toBeInTheDocument();
    expect(screen.queryByLabelText("回复客户")).not.toBeInTheDocument();
  });

  it("AC-38 关闭 409 时提示且保持现状", async () => {
    mockRoutes(
      baseRoutes({
        "POST /api/workspace/conversations/conv-1/close": () =>
          json({ code: "CONVERSATION_CLOSED", message: "会话已结束" }, 409),
      }),
    );
    render(<ConversationGate conversationId="conv-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "关闭会话" }));

    expect(await screen.findByText("会话已结束，无法操作。")).toBeInTheDocument();
    expect(screen.getByText("人工接入中")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关闭会话" })).toBeInTheDocument();
  });

  it("AC-38 转回 404 时提示状态已变化", async () => {
    mockRoutes(
      baseRoutes({
        "POST /api/workspace/conversations/conv-1/return-to-ai": () =>
          json({ code: "NOT_FOUND", message: "未找到" }, 404),
      }),
    );
    render(<ConversationGate conversationId="conv-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "转回 AI" }));

    expect(await screen.findByText("会话状态已变化，请刷新后重试。")).toBeInTheDocument();
    expect(screen.getByText("人工接入中")).toBeInTheDocument();
  });

  it("AC-38 已领取未接管不显示关闭与转回入口", async () => {
    mockRoutes(
      baseRoutes({
        "/api/workspace/conversations/conv-1": () => json(claimedDetail),
        "/api/workspace/conversations/conv-1/messages": messagesRoute({
          conversation_id: "conv-1",
          status: "CLAIMED",
          after_id: 0,
          messages: [],
        }),
      }),
    );
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByRole("button", { name: "接管会话" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "关闭会话" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "转回 AI" })).not.toBeInTheDocument();
  });

  it("AC-38 已结束不显示关闭与转回入口且待办按快照隐藏", async () => {
    mockRoutes(
      baseRoutes({
        "/api/workspace/conversations/conv-1": () => json(closedDetail),
        "/api/workspace/conversations/conv-1/messages": messagesRoute({
          conversation_id: "conv-1",
          status: "CLOSED",
          after_id: 4,
          messages: [],
        }),
      }),
    );
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("已结束")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "关闭会话" })).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "转回 AI" })).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
