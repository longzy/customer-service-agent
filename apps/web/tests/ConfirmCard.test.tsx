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
    expect(screen.getByText("正在提交")).toBeInTheDocument();
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

describe("ConfirmCard 终态覆盖", () => {
  const base: Cancellation = {
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

  it.each([
    ["REJECTED", "取消申请被拒绝"],
    ["MANUAL_REVIEW", "已转人工处理"],
    ["ABANDONED", "未提交（已放弃）"],
    ["ELIGIBILITY_REJECTED", "不可取消，并说明原因"],
  ])("终态 %s 展示后端文案（AC-16）", (state, text) => {
    render(
      <ConfirmCard
        cancellation={{ ...base, state, state_text: text, reason_code: "SHIPPED" }}
        busy={false}
        onConfirm={vi.fn()}
        onAbandon={vi.fn()}
      />,
    );
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "确认取消" })).not.toBeInTheDocument();
  });
});

describe("ConfirmCard 结果文案（AC-16）", () => {
  const base: Cancellation = {
    task_id: "task-1",
    state: "AWAITING_CONFIRMATION",
    state_text: "等待您确认",
    reason_code: null,
    reason_text: null,
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

  it("资格拒绝展示原因与下一步，不展示原因码（AC-16）", () => {
    render(
      <ConfirmCard
        cancellation={{
          ...base,
          state: "ELIGIBILITY_REJECTED",
          state_text: "不可取消，并说明原因",
          reason_code: "SHIPPED",
          reason_text: "订单已发货",
          next_step: "如需进一步处理，可转人工。",
        }}
        busy={false}
        onConfirm={vi.fn()}
        onAbandon={vi.fn()}
      />,
    );
    expect(screen.getByText("原因：订单已发货")).toBeInTheDocument();
    expect(screen.getByText("如需进一步处理，可转人工。")).toBeInTheDocument();
    expect(screen.queryByText(/SHIPPED/)).not.toBeInTheDocument();
  });

  it("已取消终态展示下一步（AC-16）", () => {
    render(
      <ConfirmCard
        cancellation={{
          ...base,
          state: "CANCELLED",
          state_text: "已取消",
          next_step: "如需帮助，可转人工。",
        }}
        busy={false}
        onConfirm={vi.fn()}
        onAbandon={vi.fn()}
      />,
    );
    expect(screen.getByText("已取消")).toBeInTheDocument();
    expect(screen.getByText("如需帮助，可转人工。")).toBeInTheDocument();
  });

  it("提交中只展示状态标签（AC-16）", () => {
    render(
      <ConfirmCard
        cancellation={{
          ...base,
          state: "SUBMITTING",
          state_text: "正在提交取消申请",
          next_step: "请稍候，无需重复提交。",
        }}
        busy={false}
        onConfirm={vi.fn()}
        onAbandon={vi.fn()}
      />,
    );
    expect(screen.getByText("正在提交取消申请")).toBeInTheDocument();
    expect(screen.queryByText("请稍候，无需重复提交。")).not.toBeInTheDocument();
  });
});
