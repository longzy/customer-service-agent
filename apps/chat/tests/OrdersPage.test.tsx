// AC-59
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OrdersPage } from "@/features/orders";

const replace = vi.fn();
const push = vi.fn();
// useRouter/useSearchParams 必须返回模块级稳定引用：hook 的 useCallback 依赖它们。
const router = { replace, push };
const searchParams = { get: () => null };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}));

const ORDERS = [
  {
    order_id: "ORD-10002",
    item_summary: "机械键盘 × 1",
    order_status: "FULFILLING",
    status_label: "备货中",
    amount_cents: 69900,
    currency: "CNY",
    created_at: "2026-11-11T03:00:00Z",
    created_at_local: "2026-11-11 11:00",
    cancelable: false,
  },
  {
    order_id: "ORD-10001",
    item_summary: "无线耳机 × 1",
    order_status: "PAID_UNFULFILLED",
    status_label: "已支付未发货",
    amount_cents: 39900,
    currency: "CNY",
    created_at: "2026-11-10T02:00:00Z",
    created_at_local: "2026-11-10 10:00",
    cancelable: true,
  },
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("OrdersPage", () => {
  beforeEach(() => {
    replace.mockReset();
    push.mockReset();
    vi.restoreAllMocks();
  });

  it("AC-59 展示最近订单的订单号、商品、状态、金额与下单时间", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce(json({ orders: ORDERS }));

    render(<OrdersPage />);

    expect(await screen.findByRole("heading", { name: "我的订单" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "ORD-10002" })).toBeInTheDocument();
    expect(screen.getByText("机械键盘 × 1")).toBeInTheDocument();
    expect(screen.getByText("备货中")).toBeInTheDocument();
    expect(screen.getByText("¥699.00")).toBeInTheDocument();
    expect(screen.getByText("2026-11-11 11:00")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "ORD-10001" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/orders?limit=5");
  });

  it("AC-59 加载中显示加载态", async () => {
    let resolveOrders: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveOrders = resolve;
    });
    vi.spyOn(global, "fetch").mockImplementationOnce(() => pending);

    render(<OrdersPage />);

    expect(screen.getByRole("status")).toHaveTextContent("正在加载订单");
    resolveOrders(json({ orders: [] }));
    expect(await screen.findByText("你名下暂时没有订单")).toBeInTheDocument();
  });

  it("AC-59 空列表显示明确空态，不写“暂无数据”", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(json({ orders: [] }));

    render(<OrdersPage />);

    expect(await screen.findByText("你名下暂时没有订单")).toBeInTheDocument();
    expect(screen.queryByText("暂无数据")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "返回聊天" })).toBeInTheDocument();
  });

  it("AC-59 加载失败显示可重试提示，重试成功后渲染列表", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(
        json(
          {
            code: "DEPENDENCY_UNAVAILABLE",
            retryable: true,
            visible: true,
            message: "服务暂时不可用，请稍后重试",
          },
          503,
        ),
      )
      .mockResolvedValueOnce(json({ orders: ORDERS }));

    render(<OrdersPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("订单加载失败");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    expect(await screen.findByText("ORD-10002")).toBeInTheDocument();
  });

  it("AC-67 已受理任务可在列表刷新到最终结果", async () => {
    const acceptedOrder = {
      ...ORDERS[1],
      cancellation: {
        id: "task-1",
        state: "ACCEPTED",
        status_text: "已受理，等待最终取消结果",
        next_step: "如需帮助，可转人工。",
        expires_at: "2026-11-24T10:00:00Z",
        can_confirm: false,
      },
    };
    const cancelledOrder = {
      ...ORDERS[1],
      order_status: "CANCELLED",
      status_label: "已取消",
      cancelable: false,
    };
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json({ orders: [acceptedOrder] }))
      .mockResolvedValueOnce(
        json({
          id: "task-1",
          order_id: "ORD-10001",
          state: "CANCELLED",
          status_text: "已取消",
          reason_text: null,
          next_step: "如需帮助，可转人工。",
          reply: "已取消。如需帮助，可转人工。",
          expires_at: "2026-11-24T10:00:00Z",
          confirmed_at: "2026-11-23T10:00:00Z",
          confirmation_source: "BUTTON",
          can_confirm: false,
        }),
      )
      .mockResolvedValueOnce(json({ orders: [cancelledOrder] }));

    render(<OrdersPage />);

    expect(await screen.findByText("已受理，等待最终取消结果")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刷新结果" }));

    expect(await screen.findByText("已取消")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "刷新结果" })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/customer/cancellations/task-1/refresh", {
      method: "POST",
    });
  });

  it("AC-59 未登录时跳转登录页", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({ code: "SESSION_INVALID", message: "登录已失效，请重新登录" }, 401),
    );

    render(<OrdersPage />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("AC-59 返回聊天", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(json({ orders: ORDERS }));

    render(<OrdersPage />);
    expect(await screen.findByText("ORD-10002")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "返回聊天" }));
    expect(push).toHaveBeenCalledWith("/chat");
  });
});
