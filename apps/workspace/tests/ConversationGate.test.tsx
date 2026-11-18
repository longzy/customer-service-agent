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

const humanDetail = { ...detail, status: "HUMAN_ACTIVE" };

const claimedMessages = {
  conversation_id: "conv-1",
  status: "CLAIMED",
  after_id: 0,
  messages: [],
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

/** 按 pathname 分流 mock：页面现在同时请求详情与消息轮询，按顺序 mock 会错位。 */
function mockRoutes(routes: Record<string, RouteHandler>) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const raw = typeof input === "string" ? input : input.toString();
    const path = raw.split("?")[0];
    const method = (init?.method ?? "GET").toUpperCase();
    // 先按“方法 + 路径”匹配，避免把 GET 误当成 POST 的接管/回复。
    const handler = routes[`${method} ${path}`] ?? routes[path];
    if (!handler) {
      return json({ code: "NOT_FOUND", message: "未找到" }, 404);
    }
    return handler(init);
  });
}

function detailRoute() {
  return () => json(detail);
}

function messagesRoute(page: unknown = { ...messagePage, messages: [] }) {
  return () => json(page);
}

describe("工作台 ConversationGate", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("未登录时跳转 /login", async () => {
    mockRoutes({
      "/api/workspace/session": () => json({ code: "SESSION_INVALID", message: "未登录" }, 401),
    });
    render(<ConversationGate conversationId="conv-1" />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("显示领取者可见的客户与交接单上下文", async () => {
    mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": detailRoute(),
      "/api/workspace/conversations/conv-1/messages": messagesRoute(claimedMessages),
    });
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
    mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": () =>
        json({ code: "NOT_FOUND", message: "未找到" }, 404),
    });
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("未找到该会话")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回队列" })).toBeInTheDocument();
  });

  it("AC-36 接管成功后会话语义变为人工接入中", async () => {
    const fetchMock = mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": detailRoute(),
      "/api/workspace/conversations/conv-1/messages": messagesRoute(claimedMessages),
      "POST /api/workspace/conversations/conv-1/takeover": () =>
        json({ conversation_id: "conv-1", status: "HUMAN_ACTIVE" }),
    });
    render(<ConversationGate conversationId="conv-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "接管会话" }));

    expect(await screen.findByText("已接管会话，客户将看到“人工已接入”。")).toBeInTheDocument();
    expect(screen.getByText("人工接入中")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "接管会话" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/workspace/conversations/conv-1/takeover", {
      method: "POST",
    });
  });

  it("AC-36 接管返回 404 时提示状态已变化", async () => {
    mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": detailRoute(),
      "/api/workspace/conversations/conv-1/messages": messagesRoute(claimedMessages),
      "POST /api/workspace/conversations/conv-1/takeover": () =>
        json({ code: "NOT_FOUND", message: "未找到" }, 404),
    });
    render(<ConversationGate conversationId="conv-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "接管会话" }));

    expect(await screen.findByText("会话状态已变化，请刷新后重试。")).toBeInTheDocument();
    expect(screen.getByText("已领取，等待接管")).toBeInTheDocument();
  });

  it("AC-37 已接管时展示实时消息并可回复", async () => {
    mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": () => json(humanDetail),
      "/api/workspace/conversations/conv-1/messages": messagesRoute(messagePage),
    });
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("您好，我是坐席 1")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("回复客户"), {
      target: { value: "请问有什么可以帮您？" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/workspace/conversations/conv-1/messages",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            "Content-Type": "application/json",
            "Idempotency-Key": expect.any(String),
          }),
        }),
      ),
    );
  });

  it("AC-37 发送回复不推进轮询游标，避免跳过客户消息", async () => {
    const fetchMock = mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": () => json(humanDetail),
      "/api/workspace/conversations/conv-1/messages": () => json(messagePage),
      "POST /api/workspace/conversations/conv-1/messages": () =>
        json({ ...messagePage, after_id: 5, messages: [{ ...messagePage.messages[0], id: 5 }] }),
    });
    render(<ConversationGate conversationId="conv-1" />);

    await screen.findByText("您好，我是坐席 1");
    fireEvent.change(screen.getByLabelText("回复客户"), { target: { value: "收到" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workspace/conversations/conv-1/messages",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    // 等至少一轮 3s 轮询，确认游标仍停在 4（首次消息页 after_id）而不是回复的 5。
    await new Promise((resolve) => setTimeout(resolve, 3300));
    const messageUrls = fetchMock.mock.calls
      .map(([input]) => String(input))
      .filter((url) => url.includes("/messages?after_id="));
    expect(messageUrls.at(-1)).toContain("after_id=4");
  });

  it("AC-37 已领取未接管时不显示回复框", async () => {
    mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": detailRoute(),
      "/api/workspace/conversations/conv-1/messages": messagesRoute(claimedMessages),
    });
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("接管后可以回复客户。")).toBeInTheDocument();
    expect(screen.queryByLabelText("回复客户")).not.toBeInTheDocument();
  });

  it("AC-37 回复 409 会话已结束时提示且不清空草稿", async () => {
    mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": () => json(humanDetail),
      "/api/workspace/conversations/conv-1/messages": messagesRoute(messagePage),
    });
    render(<ConversationGate conversationId="conv-1" />);

    await screen.findByText("您好，我是坐席 1");
    const input = screen.getByLabelText("回复客户");
    fireEvent.change(input, { target: { value: "这条会失败" } });
    vi.mocked(global.fetch).mockImplementation(async (input, init) => {
      const raw = typeof input === "string" ? input : input.toString();
      if (raw.endsWith("/messages") && init?.method === "POST") {
        return json({ code: "CONVERSATION_CLOSED", message: "会话已结束" }, 409);
      }
      return json(messagePage);
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("会话已结束，无法回复。")).toBeInTheDocument();
    expect(input).toHaveValue("这条会失败");
  });

  it("退出后回登录页", async () => {
    mockRoutes({
      "/api/workspace/session": () => json(session),
      "/api/workspace/conversations/conv-1": () => json(humanDetail),
      "/api/workspace/conversations/conv-1/messages": messagesRoute(),
      "/api/workspace/sessions": () => new Response(null, { status: 204 }),
    });
    render(<ConversationGate conversationId="conv-1" />);

    expect(await screen.findByText("conv-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
