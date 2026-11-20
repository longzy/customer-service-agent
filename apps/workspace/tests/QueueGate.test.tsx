import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { QueueGate } from "@/features/queue";

const replace = vi.fn();
const push = vi.fn();
const router = { replace, push };

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
    push.mockReset();
    vi.restoreAllMocks();
  });

  it("AC-44 未登录时跳转 /login", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({ code: "SESSION_INVALID", message: "未登录" }, 401),
    );
    render(<QueueGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("AC-46 已登录且队列为空时展示坐席与空队列，退出后跳转 /login", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [] }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<QueueGate />);
    expect(await screen.findByText("坐席 1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "待接入队列" })).toBeInTheDocument();
    expect(screen.getByText("队列已清空")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledWith("/api/workspace/sessions", { method: "DELETE" });
  });

  it("AC-44 按等待时长降序渲染队列摘要", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: queueItems }));
    render(<QueueGate />);

    expect((await screen.findAllByText("客户甲")).length).toBeGreaterThan(0);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("客户甲");
    expect(rows[0]).toHaveTextContent("客户要求转人工");
    expect(rows[0]).toHaveTextContent("0 分 12 秒");
    expect(rows[0]).toHaveTextContent("转人工");
    expect(rows[1]).toHaveTextContent("客户乙");
    expect(rows[1]).toHaveTextContent("AI 置信度不足");
    expect(rows[1]).toHaveTextContent("0 分 07 秒");
    expect(rows[1]).toHaveTextContent("我的订单到哪了，手机 138****5678");
  });

  it("AC-46 队列接口 401 时回登录页", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID", message: "未登录" }, 401));
    render(<QueueGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("AC-45 选中行打开抽屉并展示摘要详情", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: queueItems }));
    render(<QueueGate />);
    const rows = await screen.findAllByRole("row");

    // 抽屉模式下默认不选中；点击行才打开会话详情抽屉
    expect(screen.queryByLabelText("会话详情")).not.toBeInTheDocument();
    fireEvent.click(rows[1]);
    const detail = await screen.findByLabelText("会话详情");
    await waitFor(() => expect(within(detail).getByText("最后一条消息")).toBeInTheDocument());
    expect(within(detail).getByText("领取后进入会话页")).toBeInTheDocument();
    expect(within(detail).getByText("领取规则")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "查看完整交接单" })).not.toBeInTheDocument();
  });

  it("AC-47 J/K 切换选中，Esc 清除", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: queueItems }));
    render(<QueueGate />);
    await screen.findAllByText("客户甲");

    // 抽屉模态会把背景标记 aria-hidden，用 hidden:true 读取行的选中态
    const dataRows = () => screen.getAllByRole("row", { hidden: true }).slice(1);
    fireEvent.click(dataRows()[0]);
    await waitFor(() => expect(dataRows()[0]).toHaveAttribute("aria-selected", "true"));

    fireEvent.keyDown(document.body, { key: "j" });
    await waitFor(() => expect(dataRows()[1]).toHaveAttribute("aria-selected", "true"));

    fireEvent.keyDown(document.body, { key: "Escape" });
    await waitFor(() =>
      expect(dataRows().some((row) => row.getAttribute("aria-selected") === "true")).toBe(false),
    );
  });

  it("AC-46 队列请求失败时显示可重试提示", async () => {
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
    expect(await screen.findByText("队列已清空")).toBeInTheDocument();
  });

  it("AC-46 网络错误时显示可重试提示", async () => {
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
    expect(await screen.findByText("坐席 1")).toBeInTheDocument();
    expect(await screen.findByText("队列已清空")).toBeInTheDocument();
  });

  it("AC-44 领取成功后进入会话页", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [queueItems[0]] }))
      .mockResolvedValueOnce(
        json({ handoff_id: "ho-1", conversation_id: "conv-1", status: "CLAIMED" }),
      );
    render(<QueueGate />);
    fireEvent.click(await screen.findByRole("button", { name: "领取 客户甲 的会话" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/conversations/conv-1"));
    expect(fetchMock).toHaveBeenCalledWith("/api/workspace/queue/ho-1/claim", {
      method: "POST",
    });
  });

  it("AC-44 领取冲突时提示并刷新队列", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [queueItems[0]] }))
      .mockResolvedValueOnce(
        json({ code: "CLAIM_CONFLICT", message: "该会话已被其他坐席领取" }, 409),
      )
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [] }));
    render(<QueueGate />);
    fireEvent.click(await screen.findByRole("button", { name: "领取 客户甲 的会话" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "该会话已被其他坐席领取，队列已刷新",
    );
    expect(await screen.findByText("队列已清空")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("AC-44 领取返回 401 时回登录页", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [queueItems[0]] }))
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID", message: "未登录" }, 401));
    render(<QueueGate />);
    fireEvent.click(await screen.findByRole("button", { name: "领取 客户甲 的会话" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("AC-44 领取 404 时提示已领取并刷新", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [queueItems[0]] }))
      .mockResolvedValueOnce(json({ code: "NOT_FOUND", message: "未找到" }, 404))
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [] }));
    render(<QueueGate />);
    fireEvent.click(await screen.findByRole("button", { name: "领取 客户甲 的会话" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "该交接单不存在或已被领取，队列已刷新",
    );
  });

  it("AC-46 非坐席 403 显示无权限而不是回登录页", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "FORBIDDEN", message: "无权访问" }, 403));
    render(<QueueGate />);

    expect(await screen.findByText("无权访问该队列")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalledWith("/login");
  });

  it("AC-46 错误态保留接口错误码", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ code: "QUEUE_UNAVAILABLE", message: "系统异常" }, 500));
    render(<QueueGate />);

    expect(await screen.findByText("QUEUE_UNAVAILABLE")).toBeInTheDocument();
  });

  it("AC-47 J/K 真实按键移动选中", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: queueItems }));
    render(<QueueGate />);
    await screen.findAllByText("客户甲");

    const dataRows = () => screen.getAllByRole("row", { hidden: true }).slice(1);
    fireEvent.keyDown(document.body, { key: "j" });
    await waitFor(() => expect(dataRows()[0]).toHaveAttribute("aria-selected", "true"));
    fireEvent.keyDown(document.body, { key: "j" });
    await waitFor(() => expect(dataRows()[1]).toHaveAttribute("aria-selected", "true"));
    fireEvent.keyDown(document.body, { key: "k" });
    await waitFor(() => expect(dataRows()[0]).toHaveAttribute("aria-selected", "true"));
  });

  it("AC-47 ⌘K 聚焦搜索框且 Enter 领取选中行", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [queueItems[0]] }))
      .mockResolvedValueOnce(
        json({ handoff_id: "ho-1", conversation_id: "conv-1", status: "CLAIMED" }),
      );
    render(<QueueGate />);
    await screen.findByText("客户甲");
    fireEvent.keyDown(document.body, { key: "j" });
    await waitFor(() =>
      expect(screen.getAllByRole("row", { hidden: true })[1]).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );

    const search = screen.getByLabelText("搜索客户、账号或会话 ID");
    fireEvent.keyDown(document.body, { key: "k", metaKey: true });
    await waitFor(() => expect(search).toHaveFocus());

    (search as HTMLInputElement).blur();
    fireEvent.keyDown(document.body, { key: "Enter" });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/conversations/conv-1"));
  });

  it("AC-45 详情面板领取按钮进入会话页", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [queueItems[0]] }))
      .mockResolvedValueOnce(
        json({ handoff_id: "ho-1", conversation_id: "conv-1", status: "CLAIMED" }),
      );
    render(<QueueGate />);
    const rows = await screen.findAllByRole("row");
    fireEvent.click(rows[1]);
    await waitFor(() => expect(screen.getByRole("button", { name: "领取会话" })).toBeEnabled());

    fireEvent.click(screen.getByRole("button", { name: "领取会话" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/conversations/conv-1"));
  });

  it("AC-44 超时行标记与排序切换", async () => {
    const overtime = { ...queueItems[0], handoff_id: "ho-3", waiting_seconds: 301 };
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: [overtime, queueItems[1]] }));
    render(<QueueGate />);
    const overtimeRows = await screen.findAllByRole("row");
    expect(within(overtimeRows[1]).getByText("已超时")).toBeInTheDocument();

    // HeroUI Select 是复合组件：可见触发器为 button，点击后从列表选中 option
    fireEvent.click(screen.getByRole("button", { name: /排序方式/ }));
    fireEvent.click(await screen.findByRole("option", { name: "最新进入" }));
    await waitFor(() => {
      const rows = screen.getAllByRole("row").slice(1);
      expect(rows[0]).toHaveTextContent("客户乙");
    });
  });

  it("AC-44 搜索会话 ID 命中", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: queueItems }));
    render(<QueueGate />);
    await screen.findAllByText("客户甲");

    fireEvent.change(screen.getByLabelText("搜索客户、账号或会话 ID"), {
      target: { value: "conv-2" },
    });
    await waitFor(() => {
      const rows = screen.getAllByRole("row").slice(1);
      expect(rows).toHaveLength(1);
      expect(rows[0]).toHaveTextContent("客户乙");
    });
  });

  it("AC-44 超过 10 条时显示 HeroUI Pagination 并可翻页", async () => {
    const many = Array.from({ length: 12 }, (_, index) => ({
      handoff_id: `ho-${index + 1}`,
      conversation_id: `conv-${index + 1}`,
      customer_username: `customer_${index + 1}`,
      customer_display_name: `客户${index + 1}`,
      waiting_seconds: 12 - index,
      reason: "CUSTOMER_REQUEST",
      order_count: 0,
      last_message: `消息 ${index + 1}`,
    }));
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(json({ items: many }));
    render(<QueueGate />);
    await screen.findAllByText("客户1");

    expect(screen.getByRole("navigation", { name: "队列分页" })).toBeInTheDocument();
    expect(screen.getAllByRole("row").slice(1)).toHaveLength(10);

    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    await waitFor(() => {
      const rows = screen.getAllByRole("row").slice(1);
      expect(rows).toHaveLength(2);
      expect(rows[0]).toHaveTextContent("客户11");
    });
  });
});
