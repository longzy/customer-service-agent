import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueryView } from "@/components/QueryView";

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

describe("QueryView", () => {
  it("展示订单号、状态文案与金额（AC-01）", () => {
    render(<QueryView orders={[order]} />);
    expect(screen.getByText("ORD-10001")).toBeInTheDocument();
    expect(screen.getByText("待发货")).toBeInTheDocument();
    expect(screen.getByText("无线耳机 × 1")).toBeInTheDocument();
    expect(screen.getByText("¥399.00")).toBeInTheDocument();
  });
});
