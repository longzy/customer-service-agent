import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmCard, type Cancellation } from "@/components/ConfirmCard";

const card: Cancellation = {
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

describe("ConfirmCard", () => {
  it("展示订单号、商品、状态与影响（AC-04）", () => {
    render(
      <ConfirmCard cancellation={card} busy={false} onConfirm={vi.fn()} onAbandon={vi.fn()} />,
    );
    expect(screen.getByText("ORD-10001")).toBeInTheDocument();
    expect(screen.getByText("无线耳机 × 1")).toBeInTheDocument();
    expect(screen.getByText("待发货")).toBeInTheDocument();
    expect(screen.getByText("不可撤销")).toBeInTheDocument();
    expect(screen.getByText(/确认后将向订单系统提交/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认取消" })).toBeEnabled();
  });

  it("确认调用回调（AC-05）", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmCard cancellation={card} busy={false} onConfirm={onConfirm} onAbandon={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "确认取消" }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("提交中禁用按钮（AC-05）", () => {
    render(
      <ConfirmCard
        cancellation={{ ...card, state: "SUBMITTING", state_text: "正在提交" }}
        busy={false}
        onConfirm={vi.fn()}
        onAbandon={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "确认取消" })).toBeDisabled();
    expect(screen.getByText("已提交，正在核实受理结果")).toBeInTheDocument();
  });

  it("终态收起卡片（AC-16）", () => {
    render(
      <ConfirmCard
        cancellation={{ ...card, state: "CANCELLED", state_text: "已取消" }}
        busy={false}
        onConfirm={vi.fn()}
        onAbandon={vi.fn()}
      />,
    );
    expect(screen.getByText("已取消")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认取消" })).not.toBeInTheDocument();
  });
});
