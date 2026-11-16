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

function reply(overrides: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      conversation_id: "conv-1",
      reply: "订单 ORD-10001：无线耳机 × 1，状态 待发货，金额 399.00 元。",
      orders: [order],
      clarification: [],
      ...overrides,
    }),
    { status: 200 },
  );
}

async function send(text: string) {
  fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
}

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
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(reply());
    render(<ChatShell />);
    await send("查一下 ORD-10001");

    expect(await screen.findByText("查一下 ORD-10001")).toBeInTheDocument();
    expect(await screen.findByText(/订单 ORD-10001/)).toBeInTheDocument();
    expect(screen.getByText("待发货")).toBeInTheDocument();
    const body = JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string);
    expect(body).toEqual({ content: "查一下 ORD-10001", conversation_id: null });
  });

  it("后续消息回传会话 id（AC-01）", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(reply())
      .mockResolvedValueOnce(reply());
    render(<ChatShell />);
    await send("第一句");
    await screen.findByText(/订单 ORD-10001/);
    fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: "第二句" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string);
    expect(body.conversation_id).toBe("conv-1");
  });

  it("澄清候选可见（AC-08）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      reply({
        orders: [],
        reply: "你提到了多笔订单，请确认是哪一笔：ORD-10001、ORD-10002",
        clarification: ["ORD-10001", "ORD-10002"],
      }),
    );
    render(<ChatShell />);
    await send("查 ORD-10001 和 ORD-10002");
    expect(await screen.findByText(/候选：ORD-10001、ORD-10002/)).toBeInTheDocument();
  });

  it("服务不可用时显示可重试提示（基座豁免）", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 503 }))
      .mockResolvedValueOnce(reply());
    render(<ChatShell />);
    await send("查订单");
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText(/订单 ORD-10001/)).toBeInTheDocument();
    const retryBody = JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string);
    expect(retryBody.content).toBe("查订单");
    expect(screen.getAllByText("查订单")).toHaveLength(1);
  });

  it("网络异常显示可重试提示（基座豁免）", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new TypeError("failed"));
    render(<ChatShell />);
    await send("查订单");
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成");
  });

  it("登录失效时跳转登录页（AC-20）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));
    render(<ChatShell />);
    await send("查订单");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("Enter 发送、Shift+Enter 换行（基座豁免）", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue(reply());
    render(<ChatShell />);
    const textarea = screen.getByLabelText("输入消息");
    fireEvent.change(textarea, { target: { value: "第一行" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("请求中禁用输入与发送（基座豁免）", async () => {
    vi.spyOn(global, "fetch").mockImplementation(() => new Promise(() => {}));
    render(<ChatShell />);
    await send("查订单");
    expect(screen.getByLabelText("输入消息")).toBeDisabled();
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("正在查询");
  });
});

describe("ChatShell 取消卡片", () => {
  const cancellation = {
    task_id: "task-1",
    state: "AWAITING_CONFIRMATION",
    state_text: "等待您确认",
    reason_code: null,
    expires_at: "2026-11-15T12:00:00Z",
    order: {
      order_id: "ORD-10001",
      item_summary: "无线耳机 × 1",
      status_text: "待发货",
      amount_cents: 39900,
      currency: "CNY",
    },
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("取消意图显示确认卡片并可确认（AC-04、AC-05）", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            conversation_id: "conv-1",
            reply: "等待您确认",
            orders: [],
            clarification: [],
            cancellation,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            state: "ACCEPTED",
            state_text: "已受理，等待最终取消结果",
            reason_code: null,
          }),
          { status: 200 },
        ),
      );
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), {
      target: { value: "取消 ORD-10001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByRole("button", { name: "确认取消" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认取消" }));
    expect(await screen.findByText("已受理，等待最终取消结果")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/cancellation-requests/task-1/confirm", {
      method: "POST",
    });
  });
});

describe("ChatShell 取消动作失败", () => {
  const cancellation = {
    task_id: "task-2",
    state: "AWAITING_CONFIRMATION",
    state_text: "等待您确认",
    reason_code: null,
    expires_at: "2026-11-15T12:00:00Z",
    order: {
      order_id: "ORD-10001",
      item_summary: "无线耳机 × 1",
      status_text: "待发货",
      amount_cents: 39900,
      currency: "CNY",
    },
  };

  async function renderCard() {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversation_id: "conv-1",
          reply: "等待您确认",
          orders: [],
          cancellation,
        }),
        { status: 200 },
      ),
    );
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: "取消 ORD-10001" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByRole("button", { name: "确认取消" });
  }

  it("不取消调用放弃接口（AC-06）", async () => {
    await renderCard();
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          state: "ABANDONED",
          state_text: "未提交（已放弃）",
          reason_code: null,
          reason_text: null,
          next_step: "如仍需取消，可重新发起。",
        }),
        { status: 200 },
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "不取消" }));
    expect(await screen.findByText("未提交（已放弃）")).toBeInTheDocument();
    expect(screen.getByText("如仍需取消，可重新发起。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/cancellation-requests/task-2/abandon", {
      method: "POST",
    });
  });

  it("确认冲突时查询最新状态（AC-05）", async () => {
    await renderCard();
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 409 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            state: "ELIGIBILITY_REJECTED",
            state_text: "不可取消，并说明原因",
            reason_code: "SHIPPED",
            reason_text: "订单已发货",
            next_step: "如需进一步处理，可转人工。",
          }),
          { status: 200 },
        ),
      );
    fireEvent.click(screen.getByRole("button", { name: "确认取消" }));
    expect(await screen.findByText("不可取消，并说明原因")).toBeInTheDocument();
    expect(screen.getByText("原因：订单已发货")).toBeInTheDocument();
    expect(screen.getByText("如需进一步处理，可转人工。")).toBeInTheDocument();
  });
});

describe("ChatShell 人工转接", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("转人工后停止自动回复（AC-13）", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            conversation_id: "conv-9",
            reply: "订单 ORD-10001：无线耳机 × 1",
            orders: [order],
            clarification: [],
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "h-1" }), { status: 201 }));
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: "查 ORD-10001" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText(/订单 ORD-10001/);
    fireEvent.click(screen.getByRole("button", { name: "转人工" }));
    expect(await screen.findByText("已转人工，自动回复已停止")).toBeInTheDocument();
    expect(screen.getByLabelText("输入消息")).toBeDisabled();
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/handoff",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ conversation_id: "conv-9" }),
      }),
    );
  });
});

describe("ChatShell 已转人工的 409", () => {
  it("发送返回 409 时显示已转人工并禁用输入（AC-13）", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            conversation_id: "conv-1",
            reply: "订单 ORD-10001",
            orders: [],
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response("{}", { status: 409 }));
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: "查单" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("订单 ORD-10001");
    fireEvent.change(screen.getByLabelText("输入消息"), { target: { value: "还在吗" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("已转人工，自动回复已停止")).toBeInTheDocument();
    expect(screen.getByLabelText("输入消息")).toBeDisabled();
  });
});

describe("ChatShell 结果文案透传", () => {
  const cancellation = {
    task_id: "task-3",
    state: "AWAITING_CONFIRMATION",
    state_text: "等待您确认",
    reason_code: null,
    next_step: "请在确认卡片中选择“确认取消”或“不取消”。",
    expires_at: "2026-11-15T12:00:00Z",
    order: {
      order_id: "ORD-10001",
      item_summary: "无线耳机 × 1",
      status_text: "待发货",
      amount_cents: 39900,
      currency: "CNY",
    },
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("资格拒绝卡片保留原因与下一步（AC-16）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          conversation_id: "conv-1",
          reply: "不可取消，并说明原因：订单已发货。如需进一步处理，可转人工。",
          orders: [],
          clarification: [],
          cancellation: {
            ...cancellation,
            state: "ELIGIBILITY_REJECTED",
            state_text: "不可取消，并说明原因",
            reason_code: "SHIPPED",
            reason_text: "订单已发货",
            next_step: "如需进一步处理，可转人工。",
          },
        }),
        { status: 200 },
      ),
    );
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), {
      target: { value: "取消 ORD-10003" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("原因：订单已发货")).toBeInTheDocument();
    expect(screen.getByText("如需进一步处理，可转人工。")).toBeInTheDocument();
  });

  it("确认后卡片保留下一步（AC-16）", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            conversation_id: "conv-1",
            reply: "等待您确认。请在确认卡片中选择“确认取消”或“不取消”。",
            orders: [],
            clarification: [],
            cancellation,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            state: "CANCELLED",
            state_text: "已取消",
            reason_code: null,
            reason_text: null,
            next_step: "如需帮助，可转人工。",
          }),
          { status: 200 },
        ),
      );
    render(<ChatShell />);
    fireEvent.change(screen.getByLabelText("输入消息"), {
      target: { value: "取消 ORD-10001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认取消" }));
    expect(await screen.findByText("如需帮助，可转人工。")).toBeInTheDocument();
  });
});
