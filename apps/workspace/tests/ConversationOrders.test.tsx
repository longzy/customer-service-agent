// AC-55 AC-56 AC-58
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConversationDetailPanel } from "@/features/conversation/components/ConversationDetailPanel";
import type { ConversationDetail } from "@/features/conversation/types";

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

const KEYBOARD = {
  ...ORDER,
  order_id: "ORD-10002",
  item_summary: "机械键盘 × 1",
  order_status: "FULFILLING",
  status_label: "备货中",
  amount_cents: 69900,
  created_at_local: "2026-11-12 09:00",
};

const actions = {
  busy: false,
  acting: null,
  onTakeOver: vi.fn(),
  onClose: vi.fn(),
  onReturnToAi: vi.fn(),
};

function detailWith(
  handoff: Partial<NonNullable<ConversationDetail["handoff"]>>,
): ConversationDetail {
  return {
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
      order_context_status: "empty",
      messages: [],
      ai_trace: [],
      ...handoff,
    },
  };
}

function renderDetail(detail: ConversationDetail) {
  return render(
    <ConversationDetailPanel
      detail={detail}
      feedback={{ notice: null, error: null }}
      actions={actions}
    />,
  );
}

describe("Conversation Orders", () => {
  it("orders 四态之 ok：列出自本人订单的摘要字段", () => {
    renderDetail(
      detailWith({
        order_count: 2,
        order_context_status: "ok",
        orders: [ORDER, KEYBOARD],
      }),
    );

    expect(screen.getByRole("heading", { name: "最近订单" })).toBeInTheDocument();
    expect(screen.getByText("ORD-10001")).toBeInTheDocument();
    expect(screen.getByText("无线耳机 × 1")).toBeInTheDocument();
    expect(screen.getByText("已支付未发货")).toBeInTheDocument();
    expect(screen.getByText("¥399.00")).toBeInTheDocument();
    expect(screen.getByText("2026-11-10 10:00")).toBeInTheDocument();
    expect(screen.getByText("ORD-10002")).toBeInTheDocument();
    expect(screen.queryByText("ORD-20001")).not.toBeInTheDocument();
  });

  it("orders 四态之 empty：明确说暂无订单，而不是不可用", () => {
    renderDetail(detailWith({ order_count: 0, order_context_status: "empty", orders: [] }));

    expect(screen.getByText("该客户名下暂无订单")).toBeInTheDocument();
    expect(screen.queryByText("订单信息暂不可用")).not.toBeInTheDocument();
  });

  it("orders 四态之 failed：显示不可用提示", () => {
    renderDetail(detailWith({ order_count: 0, order_context_status: "failed", orders: [] }));

    expect(screen.getByText("订单信息暂不可用")).toBeInTheDocument();
    expect(screen.queryByText("该客户名下暂无订单")).not.toBeInTheDocument();
  });

  it("orders 四态之 unknown：说明本次未查询，不推断无订单", () => {
    renderDetail(detailWith({ order_count: 0, order_context_status: "unknown", orders: [] }));

    expect(screen.getByText("该会话未查询订单")).toBeInTheDocument();
    expect(screen.queryByText("该客户名下暂无订单")).not.toBeInTheDocument();
  });

  it("无交接单时不渲染订单区", () => {
    renderDetail({
      id: "conv-1",
      status: "AI_ACTIVE",
      customer: { username: "customer_a", display_name: "客户甲" },
      handoff: null,
    });

    expect(screen.queryByRole("heading", { name: "最近订单" })).not.toBeInTheDocument();
  });

  it("订单卡片可聚焦，键盘可定位阅读", () => {
    renderDetail(detailWith({ order_count: 1, order_context_status: "ok", orders: [ORDER] }));

    const card = screen.getByRole("article", { name: "ORD-10001" });
    card.focus();
    expect(card).toHaveFocus();
  });
});
