// AC-38：客户结束会话后只读，关闭入口消失，失败时保留输入可重试。
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatShell } from "@/features/chat";

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

const conversation = { id: "conv-1", status: "AI_ACTIVE", after_id: 0 } as const;

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
    created_at: "2026-11-18T07:00:00Z",
  };
}

function emptyPage(): unknown {
  return { conversation_id: "conv-1", status: "AI_ACTIVE", after_id: 0, messages: [] };
}

function renderShell() {
  return render(
    <ChatShell customer={customer} conversation={conversation} onLogout={vi.fn()} busy={false} />,
  );
}

describe("ChatShell 结束会话", () => {
  beforeEach(() => {
    replace.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("AC-38 点击结束会话后变为只读并停止轮询", async () => {
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
          status: "CLOSED",
          after_id: 3,
          messages: [message(3, "system", "会话已结束")],
        }),
      );

    renderShell();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("您好")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "结束会话" }));
    });

    expect(fetchMock).toHaveBeenLastCalledWith("/api/customer/session/close", {
      method: "POST",
      headers: { "Idempotency-Key": expect.any(String) },
    });
    expect(screen.getByText("已结束")).toBeInTheDocument();
    expect(screen.getByText("会话已结束")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "结束会话" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("消息")).not.toBeInTheDocument();

    const callsAfterClose = fetchMock.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(callsAfterClose);
  });

  it("AC-38 已关闭会话不显示结束入口与输入框", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({
        conversation_id: "conv-1",
        status: "CLOSED",
        after_id: 3,
        messages: [message(1, "customer", "你好"), message(3, "system", "会话已结束")],
      }),
    );

    renderShell();

    expect(await screen.findByText("已结束")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "结束会话" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("消息")).not.toBeInTheDocument();
  });

  it("AC-38 结束会话失败时保留输入并复用幂等键重试", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(emptyPage()))
      .mockResolvedValueOnce(json({ code: "INTERNAL_ERROR", message: "服务暂不可用" }, 500))
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "CLOSED",
          after_id: 3,
          messages: [message(3, "system", "会话已结束")],
        }),
      );

    renderShell();
    expect(await screen.findByText("你好，我是小回。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "结束会话" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("服务暂不可用");
    expect(screen.getByRole("button", { name: "结束会话" })).toBeEnabled();
    expect(screen.getByLabelText("消息")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "结束会话" }));
    expect(await screen.findByText("已结束")).toBeInTheDocument();

    const keys = fetchMock.mock.calls
      .filter(([url]) => url === "/api/customer/session/close")
      .map(
        ([, init]) => (init?.headers as Record<string, string> | undefined)?.["Idempotency-Key"],
      );
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBeTruthy();
    expect(keys[0]).toBe(keys[1]);
  });
});
