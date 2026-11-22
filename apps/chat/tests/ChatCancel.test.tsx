// AC-63
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MessageList } from "@/features/chat/components/MessageList";
import type { CancellationSummary } from "@/features/chat/types";
import type { Message } from "@/features/chat/types";

const ORDER = {
  order_id: "ORD-10001",
  item_summary: "无线耳机 × 1",
  order_status: "PAID_UNFULFILLED",
  status_label: "已支付未发货",
  amount_cents: 39900,
  currency: "CNY",
  created_at: "2026-11-10T02:00:00Z",
  created_at_local: "2026-11-10 10:00",
};

const AWAITING: CancellationSummary = {
  state: "AWAITING_CONFIRMATION",
  status_text: "等待您确认",
  next_step: "请在确认卡片中选择“确认取消”或“不取消”。",
  expires_at: "2026-11-23T08:00:00Z",
  can_confirm: true,
};

const ACCEPTED: CancellationSummary = {
  ...AWAITING,
  state: "ACCEPTED",
  status_text: "已受理，等待最终取消结果",
  can_confirm: false,
};

function aiMessage(orders: (typeof ORDER)[], cancellation: CancellationSummary | null): Message {
  return {
    id: 1,
    author_type: "ai",
    content: "你的订单 ORD-10001：无线耳机 × 1。尚未提交。",
    created_at: "2026-11-10T02:00:00Z",
    payload: { orders, cancellation },
  };
}

function renderMessages(messages: Message[], onCancelOrder = vi.fn()) {
  render(
    <MessageList
      messages={messages}
      loading={false}
      status="AI_ACTIVE"
      onQuick={vi.fn()}
      onCancelOrder={onCancelOrder}
    />,
  );
  return { onCancelOrder };
}

describe("聊天取消入口", () => {
  it("AC-63 自然语言取消后展示确认卡片，含订单事实、有效期与尚未提交", () => {
    const { onCancelOrder } = renderMessages([aiMessage([ORDER], AWAITING)]);

    expect(screen.getByText("ORD-10001")).toBeInTheDocument();
    expect(screen.getByText("无线耳机 × 1")).toBeInTheDocument();
    expect(screen.getByText("¥399.00")).toBeInTheDocument();
    expect(screen.getByText("尚未提交")).toBeInTheDocument();
    expect(screen.getByText(/确认有效期至/)).toBeInTheDocument();
    expect(screen.getByText(/不产生退款/)).toBeInTheDocument();
    expect(screen.getByText(/回复「确认取消」/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "去订单页确认" }));
    expect(onCancelOrder).toHaveBeenCalledWith("ORD-10001");
  });

  it("AC-63 结果消息不再出现确认按钮，只展示订单卡片", () => {
    renderMessages([aiMessage([ORDER], ACCEPTED)]);

    expect(screen.queryByText("尚未提交")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "去订单页确认" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消订单" })).toBeInTheDocument();
  });

  it("AC-63 多单候选展示多张订单卡片，不替客户选单", () => {
    const second = { ...ORDER, order_id: "ORD-10002", item_summary: "机械键盘 × 1" };
    renderMessages([aiMessage([ORDER, second], null)]);

    expect(screen.getByText("ORD-10001")).toBeInTheDocument();
    expect(screen.getByText("ORD-10002")).toBeInTheDocument();
    expect(screen.queryByText("尚未提交")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "取消订单" })).toHaveLength(2);
  });
});
