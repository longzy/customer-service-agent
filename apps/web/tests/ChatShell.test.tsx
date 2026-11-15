import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatShell } from "@/components/ChatShell";

const replace = vi.fn();
const router = { push: vi.fn(), replace };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

const order = {
  order_id: "ORD-10001",
  item_summary: "无线耳机 × 1",
  order_status: "PAID_UNFULFILLED",
  status_text: "待发货",
  amount_cents: 39900,
  currency: "CNY",
  created_at: "2026-11-10T02:00:00Z",
  cancelable: true,
};

describe("ChatShell", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("渲染空态标题与输入区（基座豁免：组件空态）", () => {
    render(<ChatShell />);
    expect(screen.getByRole("heading", { name: "客服中心" })).toBeInTheDocument();
    expect(screen.getByLabelText("输入消息")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
  });

  it("发送消息后展示用户消息、回复与订单卡片（AC-01）", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          reply: "订单 ORD-10001：无线耳机 × 1，状态 待发货，金额 399.00 元。",
          orders: [order],
          clarification: [],
        }),
        { status: 200 },
      ),
    );
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), {
      target: { value: "查一下 ORD-10001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("查一下 ORD-10001")).toBeInTheDocument();
    expect(await screen.findByText(/订单 ORD-10001/)).toBeInTheDocument();
    expect(screen.getByText("待发货")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/message",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ content: "查一下 ORD-10001" }),
      }),
    );
  });

  it("服务不可用时显示错误（AC-01）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 503 }));
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: "查订单" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("服务暂时不可用");
  });

  it("登录失效时跳转登录页（AC-20）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: "查订单" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
