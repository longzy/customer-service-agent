// AC-60 AC-61 AC-62
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MessageList } from "@/features/chat/components/MessageList";
import type { Message } from "@/features/chat/types";
import { OrdersPage } from "@/features/orders";
import type { CancellationTask, CustomerOrderSummary } from "@/features/orders/types";

const replace = vi.fn();
const push = vi.fn();
// useRouter/useSearchParams 必须返回模块级稳定引用（FE-TEST-06）。
const router = { replace, push };
let currentSearch = new URLSearchParams();
const searchParams = { get: (key: string) => currentSearch.get(key) };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}));

const ORDER: CustomerOrderSummary = {
  order_id: "ORD-10001",
  item_summary: "无线耳机 × 1",
  order_status: "PAID_UNFULFILLED",
  status_label: "已支付未发货",
  amount_cents: 39900,
  currency: "CNY",
  created_at: "2026-11-10T02:00:00Z",
  created_at_local: "2026-11-10 10:00",
  cancelable: true,
  cancellation: null,
};

const SHIPPED: CustomerOrderSummary = {
  ...ORDER,
  order_id: "ORD-10003",
  item_summary: "显示器 × 1",
  order_status: "SHIPPED",
  status_label: "已发货",
  amount_cents: 129900,
  cancelable: false,
};

const AWAITING: CancellationTask = {
  id: "task-1",
  order_id: "ORD-10001",
  state: "AWAITING_CONFIRMATION",
  status_text: "等待您确认",
  reason_text: null,
  next_step: "请在确认卡片中选择“确认取消”或“不取消”。",
  reply: "等待您确认。请在确认卡片中选择“确认取消”或“不取消”。",
  expires_at: "2026-11-23T08:00:00Z",
  confirmed_at: null,
  confirmation_source: null,
  can_confirm: true,
};

const ACCEPTED: CancellationTask = {
  ...AWAITING,
  state: "ACCEPTED",
  status_text: "已受理，等待最终取消结果",
  reply: "已受理，等待最终取消结果。如需帮助，可转人工。",
  confirmed_at: "2026-11-22T08:00:00Z",
  confirmation_source: "BUTTON",
  can_confirm: false,
};

const CANCELLED: CancellationTask = {
  ...ACCEPTED,
  state: "CANCELLED",
  status_text: "已取消",
  reply: "已取消。如需帮助，可转人工。",
};

const ABANDONED: CancellationTask = {
  ...AWAITING,
  state: "ABANDONED",
  status_text: "未提交（已放弃）",
  reply: "未提交（已放弃）。如仍需取消，可重新发起。",
  can_confirm: false,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = () => Response;

function mockFetch(routes: Record<string, Handler>) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const handler = routes[`${method} ${url}`];
    if (!handler) {
      throw new Error(`未 mock 请求：${method} ${url}`);
    }
    return handler();
  });
}

function ordersPage(orders: CustomerOrderSummary[]) {
  return () => json({ orders });
}

function aiMessage(orders: CustomerOrderSummary[]): Message {
  return {
    id: 1,
    author_type: "ai",
    content: "你名下最近订单：",
    created_at: "2026-11-10T02:00:00Z",
    payload: {
      orders: orders.map(
        ({
          order_id,
          item_summary,
          order_status,
          status_label,
          amount_cents,
          currency,
          created_at,
          created_at_local,
        }) => ({
          order_id,
          item_summary,
          order_status,
          status_label,
          amount_cents,
          currency,
          created_at,
          created_at_local,
        }),
      ),
    },
  };
}

describe("取消确认卡片", () => {
  beforeEach(() => {
    replace.mockReset();
    push.mockReset();
    currentSearch = new URLSearchParams();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("AC-60 可取消订单显示取消按钮，点击后展示尚未提交的确认卡片", async () => {
    const fetchMock = mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([ORDER]),
      "POST /api/customer/cancellations": () => json(AWAITING),
    });

    render(<OrdersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "取消订单" }));

    const dialog = await screen.findByRole("dialog", { name: "确认取消订单" });
    expect(dialog).toHaveTextContent("ORD-10001");
    expect(dialog).toHaveTextContent("无线耳机 × 1");
    expect(dialog).toHaveTextContent("¥399.00");
    expect(dialog).toHaveTextContent("尚未提交");
    expect(dialog).toHaveTextContent("确认有效期至");
    expect(screen.getByRole("button", { name: "确认取消" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "不取消" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/customer/cancellations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ order_id: "ORD-10001" }),
      }),
    );
  });

  it("AC-60 不可取消订单不显示提交按钮", async () => {
    mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([SHIPPED]),
    });

    render(<OrdersPage />);

    expect(await screen.findByText("显示器 × 1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "取消订单" })).not.toBeInTheDocument();
  });

  it("AC-61 确认后只提交一次并展示已受理，不表述为已取消或退款", async () => {
    const fetchMock = mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([ORDER]),
      "POST /api/customer/cancellations": () => json(AWAITING),
      "POST /api/customer/cancellations/task-1/confirm": () => json(ACCEPTED),
    });

    render(<OrdersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "取消订单" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认取消" }));

    const dialog = await screen.findByRole("dialog", { name: "取消结果" });
    expect(dialog).toHaveTextContent("已受理，等待最终取消结果");
    expect(dialog).not.toHaveTextContent("已取消");
    expect(dialog).not.toHaveTextContent("退款");
    expect(screen.getByRole("button", { name: "刷新结果" })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).includes("/cancellations/task-1/confirm")),
    ).toHaveLength(1);
    // 结果落地后列表静默刷新（首屏 1 次 + 刷新 1 次），而不是再次提交。
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) => url === "/api/customer/orders?limit=5"),
      ).toHaveLength(2),
    );
  });

  it("AC-61 已受理后刷新结果推进到已取消", async () => {
    mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([
        {
          ...ORDER,
          cancellation: {
            state: "AWAITING_CONFIRMATION",
            status_text: "等待您确认",
            next_step: "请在确认卡片中选择“确认取消”或“不取消”。",
            expires_at: AWAITING.expires_at,
            can_confirm: true,
          },
        },
      ]),
      "POST /api/customer/cancellations": () => json(ACCEPTED),
      "POST /api/customer/cancellations/task-1/refresh": () => json(CANCELLED),
    });

    render(<OrdersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "去确认" }));
    fireEvent.click(await screen.findByRole("button", { name: "刷新结果" }));

    const dialog = await screen.findByRole("dialog", { name: "取消结果" });
    expect(dialog).toHaveTextContent("已取消");
    expect(dialog).not.toHaveTextContent("退款");
  });

  it("AC-62 拒绝后任务结束且弹层关闭，列表恢复可取消", async () => {
    const fetchMock = mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([ORDER]),
      "POST /api/customer/cancellations": () => json(AWAITING),
      "POST /api/customer/cancellations/task-1/decline": () => json(ABANDONED),
    });

    render(<OrdersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "取消订单" }));
    fireEvent.click(await screen.findByRole("button", { name: "不取消" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/customer/orders?limit=5"));
  });

  it("AC-62 列表已有待确认任务时停在去确认，不重复显示取消按钮", async () => {
    const pending: CustomerOrderSummary = {
      ...ORDER,
      cancellation: {
        state: "AWAITING_CONFIRMATION",
        status_text: "等待您确认",
        next_step: "请在确认卡片中选择“确认取消”或“不取消”。",
        expires_at: AWAITING.expires_at,
        can_confirm: true,
      },
    };
    mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([pending]),
      "POST /api/customer/cancellations": () => json(AWAITING),
    });

    render(<OrdersPage />);
    expect(screen.queryByRole("button", { name: "取消订单" })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "去确认" }));

    expect(await screen.findByRole("dialog", { name: "确认取消订单" })).toBeInTheDocument();
  });

  it("AC-62 过期任务直接展示未提交结果，不出现确认按钮", async () => {
    mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([ORDER]),
      "POST /api/customer/cancellations": () => json(ABANDONED),
    });

    render(<OrdersPage />);
    fireEvent.click(await screen.findByRole("button", { name: "取消订单" }));

    const dialog = await screen.findByRole("dialog", { name: "取消结果" });
    expect(dialog).toHaveTextContent("未提交（已放弃）");
    expect(screen.queryByRole("button", { name: "确认取消" })).not.toBeInTheDocument();
  });

  it("AC-60 聊天订单卡片为可取消订单提供取消入口", async () => {
    const onCancelOrder = vi.fn();

    render(
      <MessageList
        messages={[aiMessage([ORDER, SHIPPED])]}
        loading={false}
        status="AI_ACTIVE"
        onQuick={vi.fn()}
        onCancelOrder={onCancelOrder}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "取消订单" }));
    expect(onCancelOrder).toHaveBeenCalledWith("ORD-10001");
    expect(screen.getAllByRole("button", { name: "取消订单" })).toHaveLength(1);
  });

  it("AC-60 聊天卡片通过取消参数打开同一确认弹层", async () => {
    currentSearch = new URLSearchParams("cancel=ORD-10001");
    mockFetch({
      "GET /api/customer/orders?limit=5": ordersPage([ORDER]),
      "POST /api/customer/cancellations": () => json(AWAITING),
    });

    render(<OrdersPage />);

    expect(await screen.findByRole("dialog", { name: "确认取消订单" })).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/orders");
  });
});
