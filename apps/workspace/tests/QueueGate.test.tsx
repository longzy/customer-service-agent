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

  it("已登录时展示坐席与队列占位，退出后跳转 /login", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json(session))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<QueueGate />);
    expect(await screen.findByText("坐席 1（agent_1）")).toBeInTheDocument();
    expect(screen.getByText("待接入队列")).toBeInTheDocument();
    expect(screen.getByText("正在等待客户转人工")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledWith("/api/workspace/sessions", { method: "DELETE" });
  });

  it("网络错误时显示可重试提示", async () => {
    let attempts = 0;
    vi.spyOn(global, "fetch").mockImplementation(async () => {
      attempts += 1;
      if (attempts === 1) {
        throw new TypeError("Failed to fetch");
      }
      return json(session);
    });
    render(<QueueGate />);
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成，请重试");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("坐席 1（agent_1）")).toBeInTheDocument();
  });
});
