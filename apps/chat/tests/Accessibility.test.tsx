import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatShell } from "@/features/chat";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
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

function renderShell() {
  return render(
    <ChatShell customer={customer} conversation={conversation} onLogout={vi.fn()} busy={false} />,
  );
}

describe("客户侧可访问性与响应式", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("AC-47 消息流 aria-live 且脉冲支持 reduced-motion", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      json({ conversation_id: "conv-1", status: "QUEUED", after_id: 0, messages: [] }),
    );
    renderShell();

    const log = await screen.findByRole("log");
    expect(log).toHaveAttribute("aria-live", "polite");
    await screen.findByText("正在为你接通人工客服");

    const pulse = document.querySelector(".animate-pulse");
    expect(pulse?.className).toContain("motion-reduce:animate-none");
  });

  it("AC-48 窄屏快捷入口自动换行且输入区固定底部", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      json({ conversation_id: "conv-1", status: "AI_ACTIVE", after_id: 0, messages: [] }),
    );
    renderShell();

    const quick = await screen.findByRole("button", { name: "查订单" });
    expect(quick.parentElement?.className).toContain("flex-wrap");
    expect(quick.closest("section")?.className).toContain("max-w-[560px]");

    const composer = screen.getByLabelText("消息").closest("form")?.parentElement;
    expect(composer?.className).toContain("max-[767px]:sticky");
  });
});
