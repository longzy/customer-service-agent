import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatShell } from "@/components/ChatShell";

const replace = vi.fn();
const router = { replace, push: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

const customer = {
  id: "cust-1",
  tenant_id: "tenant-a",
  username: "customer_a",
  display_name: "客户甲",
};

const conversation = { id: "conv-1", status: "AI_ACTIVE", after_id: 0 };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function message(id: number, authorType: string, content: string) {
  return {
    id,
    author_type: authorType,
    content,
    created_at: "2026-11-17T07:00:00Z",
  };
}

function emptyPage(afterId = 0) {
  return {
    conversation_id: "conv-1",
    status: "AI_ACTIVE",
    after_id: afterId,
    messages: [],
  };
}

function renderShell() {
  return render(
    <ChatShell customer={customer} conversation={conversation} onLogout={vi.fn()} busy={false} />,
  );
}

describe("ChatShell", () => {
  beforeEach(() => {
    replace.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("StrictMode 双调用下不丢已加载消息", async () => {
    // 每次 fetch 必须返回新的 Response：Response body 只能读一次。
    vi.spyOn(global, "fetch").mockImplementation(async () =>
      json({
        conversation_id: "conv-1",
        status: "AI_ACTIVE",
        after_id: 2,
        messages: [message(1, "customer", "你好"), message(2, "ai", "您好。")],
      }),
    );

    render(
      <StrictMode>
        <ChatShell
          customer={customer}
          conversation={conversation}
          onLogout={vi.fn()}
          busy={false}
        />
      </StrictMode>,
    );

    expect(await screen.findByText("你好")).toBeInTheDocument();
    expect(screen.getByText("您好。")).toBeInTheDocument();
  });

  it("挂载时加载历史并渲染客户与 AI 消息", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({
        conversation_id: "conv-1",
        status: "AI_ACTIVE",
        after_id: 2,
        messages: [
          message(1, "customer", "你好，我的订单还没发货"),
          message(2, "ai", "您好，请提供订单号，我帮您查询。"),
        ],
      }),
    );

    renderShell();

    expect(await screen.findByText("你好，我的订单还没发货")).toBeInTheDocument();
    expect(screen.getByText("您好，请提供订单号，我帮您查询。")).toBeInTheDocument();
    expect(screen.getByText("客服 AI")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/messages?after_id=0");
  });

  it("发送“你好”后提交 POST 并追加 AI 回复", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(emptyPage()))
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "AI_ACTIVE",
          after_id: 2,
          messages: [
            message(1, "customer", "你好"),
            message(2, "ai", "您好，请问有什么可以帮您？"),
          ],
        }),
      );

    renderShell();
    expect(await screen.findByText("还没有消息，发送第一条吧")).toBeInTheDocument();

    const input = screen.getByLabelText("消息");
    fireEvent.change(input, { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("您好，请问有什么可以帮您？")).toBeInTheDocument();
    expect(screen.getByText("你好")).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/customer/messages",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: "你好" }),
      }),
    );
  });

  it("模型失败返回 QUEUED 与系统消息时显示“排队中，请稍候”", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(emptyPage()))
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "QUEUED",
          after_id: 2,
          messages: [message(1, "customer", "你好"), message(2, "system", "排队中，请稍候")],
        }),
      );

    renderShell();
    expect(await screen.findByText("还没有消息，发送第一条吧")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("消息"), { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("QUEUED")).toBeInTheDocument();
    expect(screen.getAllByText("排队中，请稍候")).toHaveLength(1);
    expect(screen.getByText("你好")).toBeInTheDocument();
  });

  it("每 3s 用最新 after_id 轮询并去重追加", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "AI_ACTIVE",
          after_id: 2,
          messages: [message(1, "customer", "你好"), message(2, "ai", "您好")],
        }),
      )
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "AI_ACTIVE",
          after_id: 4,
          messages: [message(2, "ai", "您好"), message(4, "ai", "轮询到的新回复")],
        }),
      );

    renderShell();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("您好")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/customer/messages?after_id=0");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/customer/messages?after_id=2");
    expect(screen.getByText("轮询到的新回复")).toBeInTheDocument();
    expect(screen.getAllByText("您好")).toHaveLength(1);
  });

  it("409 显示“会话已结束”且不清空已加载历史", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "AI_ACTIVE",
          after_id: 2,
          messages: [message(1, "customer", "历史客户消息"), message(2, "ai", "历史 AI 回复")],
        }),
      )
      .mockResolvedValueOnce(
        json(
          {
            code: "CONVERSATION_CLOSED",
            retryable: false,
            visible: true,
            message: "会话已结束",
          },
          409,
        ),
      );

    renderShell();
    expect(await screen.findByText("历史 AI 回复")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("消息"), { target: { value: "还在吗" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("会话已结束");
    expect(screen.getByText("历史客户消息")).toBeInTheDocument();
    expect(screen.getByText("历史 AI 回复")).toBeInTheDocument();
  });

  it("空白、超过 500 字或发送中禁用发送按钮", async () => {
    let resolveSend: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveSend = resolve;
    });
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(emptyPage()))
      .mockImplementationOnce(() => pending);

    renderShell();
    expect(await screen.findByText("还没有消息，发送第一条吧")).toBeInTheDocument();

    const input = screen.getByLabelText("消息");
    const sendButton = screen.getByRole("button", { name: "发送" });
    expect(sendButton).toBeDisabled();

    fireEvent.change(input, { target: { value: "   " } });
    expect(sendButton).toBeDisabled();

    fireEvent.change(input, { target: { value: "字".repeat(501) } });
    expect(sendButton).toBeDisabled();
    expect(screen.getByText("501/500")).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "你好" } });
    expect(sendButton).toBeEnabled();
    fireEvent.click(sendButton);
    expect(await screen.findByRole("button", { name: "发送中…" })).toBeDisabled();

    resolveSend(
      json({
        conversation_id: "conv-1",
        status: "AI_ACTIVE",
        after_id: 1,
        messages: [message(1, "customer", "你好")],
      }),
    );
    expect(await screen.findByText("你好")).toBeInTheDocument();
  });

  it("消息接口返回 401 时跳转 /login", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({ code: "SESSION_EXPIRED", message: "会话已过期" }, 401),
    );

    renderShell();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
