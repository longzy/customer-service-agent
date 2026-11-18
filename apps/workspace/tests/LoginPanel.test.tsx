import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPanel } from "@/features/auth";

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

async function fillAndSubmit(username = "agent_1", password = "correct-horse") {
  fireEvent.change(screen.getByLabelText("工号或邮箱"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: password } });
  const button = screen.getByRole("button", { name: "登录" });
  await waitFor(() => expect(button).toBeEnabled());
  const form = button.closest("form");
  if (!form) {
    throw new Error("找不到登录表单");
  }
  fireEvent.submit(form);
}

describe("工作台 LoginPanel", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("AC-43 已有登录会话时直接跳转 /queue", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(json(session));
    render(<LoginPanel />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
  });

  it("AC-43 坐席登录成功后跳转 /queue", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID", message: "未登录" }, 401))
      .mockResolvedValueOnce(json(session));
    render(<LoginPanel />);
    await fillAndSubmit();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/workspace/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ username: "agent_1", password: "correct-horse" }),
      }),
    );
  });

  it("AC-43 密码可见切换与固定 8 小时策略", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(
      json({ code: "SESSION_INVALID", message: "未登录" }, 401),
    );
    render(<LoginPanel />);
    const input = screen.getByLabelText("密码") as HTMLInputElement;
    expect(input.type).toBe("password");

    fireEvent.click(await screen.findByRole("button", { name: "显示密码" }));
    expect(input.type).toBe("text");
    expect(screen.getByRole("button", { name: "隐藏密码" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    const keep = screen.getByLabelText(/保持登录 8 小时/) as HTMLInputElement;
    expect(keep.checked).toBe(true);
    expect(keep.disabled).toBe(true);
  });

  it("AC-43 非 agent 403 时展示无权访问并保持停留", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID" }, 401))
      .mockResolvedValueOnce(
        json(
          {
            code: "FORBIDDEN",
            retryable: false,
            visible: true,
            message: "无权访问",
          },
          403,
        ),
      );
    render(<LoginPanel />);
    await fillAndSubmit("supervisor_x");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("无权访问");
    expect(replace).not.toHaveBeenCalled();
  });
});
