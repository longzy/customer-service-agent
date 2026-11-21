// AC-58
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MessageList } from "@/features/chat/components/MessageList";
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

const SHIPPED = {
  ...ORDER,
  order_id: "ORD-10003",
  item_summary: "显示器 × 1",
  order_status: "SHIPPED",
  status_label: "已发货",
  amount_cents: 129900,
};

function aiMessage(id: number, orders: (typeof ORDER)[] | null): Message {
  return {
    id,
    author_type: "ai",
    content: "你名下最近 2 笔订单：",
    created_at: "2026-11-10T02:00:00Z",
    payload: orders === null ? null : { orders },
  };
}

function renderMessages(messages: Message[]) {
  return render(
    <MessageList messages={messages} loading={false} status="AI_ACTIVE" onQuick={vi.fn()} />,
  );
}

describe("OrderCard", () => {
  it("展示订单号、商品、状态、金额、下单时间与快照提示", () => {
    renderMessages([aiMessage(1, [ORDER])]);

    const card = screen.getByRole("article", { name: "ORD-10001" });
    expect(card).toBeInTheDocument();
    expect(screen.getByText("无线耳机 × 1")).toBeInTheDocument();
    expect(screen.getByText("已支付未发货")).toBeInTheDocument();
    expect(screen.getByText("¥399.00")).toBeInTheDocument();
    expect(screen.getByText("2026-11-10 10:00")).toBeInTheDocument();
    expect(screen.getByText("查询时状态")).toBeInTheDocument();
  });

  it("多张卡片各为一个 article，标题层级可遍历", () => {
    renderMessages([aiMessage(1, [ORDER, SHIPPED])]);

    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(2);
    expect(screen.getByRole("article", { name: "ORD-10003" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(2);
    expect(screen.getByText("¥1,299.00")).toBeInTheDocument();
  });

  it("载荷为空时不渲染卡片，只保留 AI 文案", () => {
    renderMessages([aiMessage(1, [])]);

    expect(screen.queryByRole("article", { name: /ORD-/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
    expect(screen.getByText("你名下最近 2 笔订单：")).toBeInTheDocument();
  });

  it("没有 payload 的消息不渲染卡片", () => {
    renderMessages([aiMessage(1, null)]);

    expect(screen.queryByRole("article", { name: /ORD-/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
  });

  it("未知状态用 OMS 文案兜底，不显示原始状态码", () => {
    renderMessages([
      aiMessage(1, [{ ...ORDER, order_status: "RETURNING", status_label: "退货中" }]),
    ]);

    expect(screen.getByText("退货中")).toBeInTheDocument();
    expect(screen.queryByText("RETURNING")).not.toBeInTheDocument();
  });

  it("卡片可聚焦，键盘浏览时可定位到订单", () => {
    renderMessages([aiMessage(1, [ORDER])]);

    const card = screen.getByRole("article", { name: "ORD-10001" });
    expect(card).toHaveAttribute("tabindex", "0");
    card.focus();
    expect(card).toHaveFocus();
  });
});
