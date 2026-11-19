// AC-31 AC-32
import { fireEvent, render, screen } from "@testing-library/react";
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

describe("ChatModelFailure", () => {
  beforeEach(() => {
    replace.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("AC-31 单次模型失败显示可重试提示且不进入排队", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(emptyPage()))
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "AI_ACTIVE",
          after_id: 2,
          messages: [
            message(1, "customer", "你好"),
            message(2, "system", "AI 暂时不可用，你可以重试，或说“转人工”。"),
          ],
        }),
      );

    renderShell();
    expect(await screen.findByText("你好，我是小回。")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("消息"), { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(
      await screen.findByText("AI 暂时不可用，你可以重试，或说“转人工”。"),
    ).toBeInTheDocument();
    expect(screen.getByText("AI 服务中")).toBeInTheDocument();
    expect(screen.queryByText("正在为你接通人工客服")).not.toBeInTheDocument();
  });

  it("AC-32 连续模型失败显示已转接人工提示", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(emptyPage()))
      .mockResolvedValueOnce(
        json({
          conversation_id: "conv-1",
          status: "QUEUED",
          after_id: 2,
          messages: [
            message(1, "customer", "你好"),
            message(2, "system", "AI 暂时不可用，已为你转接人工（排队中）。"),
          ],
        }),
      );

    renderShell();
    expect(await screen.findByText("你好，我是小回。")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("消息"), { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(
      await screen.findByText("AI 暂时不可用，已为你转接人工（排队中）。"),
    ).toBeInTheDocument();
    expect(screen.getByText("人工接入中")).toBeInTheDocument();
    expect(screen.getByText("正在为你接通人工客服")).toBeInTheDocument();
  });
});
