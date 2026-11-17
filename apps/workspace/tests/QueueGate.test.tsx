import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QueueGate } from "@/components/QueueGate";

const replace = vi.fn();
const router = { replace, push: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

const session = {
  employee: {
    id: "emp-agent_1",
    tenant_id: "tenant-a",
    username: "agent_1",
    display_name: "坐席 1",
    role: "agent",
  },
  expires_at: "2026-11-17T11:00:00Z",
};

const queueItems = [
  {
    handoff_id: "ho-1",
    conversation_id: "conv-1",
    customer_username: "customer_a",
    customer_display_name: "客户甲",
    waiting_seconds: 12,
    reason: "CUSTOMER_REQUEST",
    order_count: 0,
    last_message: "转人工",
  },
  {
    handoff_id: "ho-2",
    conversation_id: "conv-2",
    customer_username: "customer_b",
    customer_display_name: "客户乙",
    waiting_seconds: 7,
    reason: "LOW_CONFIDENCE",
    order_count: 0,
    last_message: "我的订单到哪了，手机 138****5678",
  },
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("工作台 QueueGate", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("未登录时跳转 /login", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({ code: "SESSION_INVALID", message: "未登录" }, 401),
    );
    render(<QueueGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("已登录且队列为空时展示坐席与空队列，退出后跳转 /login", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [] }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<QueueGate />);
    expect(await screen.findByText("坐席 1（agent_1）")).toBeInTheDocument();
    expect(screen.getByText("待接入队列")).toBeInTheDocument();
    expect(screen.getByText("暂无待接入会话")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledWith("/api/workspace/sessions", { method: "DELETE" });
  });

  it("按接口顺序渲染队列摘要且不二次排序", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: queueItems }));
    render(<QueueGate />);

    expect(await screen.findByText("客户甲（customer_a）")).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("客户甲（customer_a）");
    expect(rows[0]).toHaveTextContent("客户要求转人工");
    expect(rows[0]).toHaveTextContent("已等待 12 秒");
    expect(rows[0]).toHaveTextContent("订单数 0");
    expect(rows[0]).toHaveTextContent("转人工");
    expect(rows[1]).toHaveTextContent("客户乙（customer_b）");
    expect(rows[1]).toHaveTextContent("AI 置信度不足");
    expect(rows[1]).toHaveTextContent("已等待 7 秒");
    expect(rows[1]).toHaveTextContent("我的订单到哪了，手机 138****5678");
  });

  it("队列接口 401 时回登录页", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID", message: "未登录" }, 401));
    render(<QueueGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("队列请求失败时显示可重试提示", async () => {
    let attempts = 0;
    vi.spyOn(global, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/workspace/session") {
        return json(session);
      }
      attempts += 1;
      if (attempts === 1) {
        return json({ code: "INTERNAL_ERROR", message: "系统异常" }, 500);
      }
      return json({ items: [] });
    });
    render(<QueueGate />);
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成，请重试");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("暂无待接入会话")).toBeInTheDocument();
  });

  it("网络错误时显示可重试提示", async () => {
    let attempts = 0;
    vi.spyOn(global, "fetch").mockImplementation(async () => {
      attempts += 1;
      if (attempts === 1) {
        throw new TypeError("Failed to fetch");
      }
      if (attempts === 2) {
        return json(session);
      }
      return json({ items: [] });
    });
    render(<QueueGate />);
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成，请重试");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("坐席 1（agent_1）")).toBeInTheDocument();
    expect(await screen.findByText("暂无待接入会话")).toBeInTheDocument();
  });
});
