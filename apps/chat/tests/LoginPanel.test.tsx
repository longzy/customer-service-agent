import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPanel } from "@/features/auth";

const replace = vi.fn();
const router = { replace, push: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

const session = {
  customer: {
    id: "cust-1",
    tenant_id: "tenant-a",
    username: "customer_a",
    display_name: "客户甲",
  },
  conversation: { id: "conv-1", status: "AI_ACTIVE", after_id: 0 },
  expires_at: "2026-11-18T03:00:00Z",
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function fillAndSubmit(username = "customer_a", password = "correct-horse") {
  fireEvent.change(screen.getByLabelText("账号"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("密码"), { target: { value: password } });
  const button = screen.getByRole("button", { name: "进入对话" });
  await waitFor(() => expect(button).toBeEnabled());
  const form = button.closest("form");
  if (!form) {
    throw new Error("找不到登录表单");
  }
  fireEvent.submit(form);
}

describe("LoginPanel", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("AC-41 已有登录会话时直接跳转 /chat", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce(json(session));
    render(<LoginPanel />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat"));
  });

  it("AC-41 账号密码登录成功后跳转 /chat", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID", message: "未登录" }, 401))
      .mockResolvedValueOnce(json(session));
    render(<LoginPanel />);
    await fillAndSubmit();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat"));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/customer/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ username: "customer_a", password: "correct-horse" }),
      }),
    );
  });

  it("AC-41 登录失败时优先展示 message 并保持停留", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID" }, 401))
      .mockResolvedValueOnce(
        json(
          {
            code: "AUTH_FAILED",
            retryable: false,
            visible: true,
            detail: "服务端内部细节",
            message: "账号或密码不正确",
          },
          401,
        ),
      );
    render(<LoginPanel />);
    await fillAndSubmit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("账号或密码不正确");
    expect(alert).not.toHaveTextContent("服务端内部细节");
    expect(replace).not.toHaveBeenCalled();
  });


  it("AC-41 密码可见切换有可访问名称", async () => {
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
  });

  it("AC-41 提交中禁用登录按钮", async () => {
    let resolveLogin: (value: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => {
      resolveLogin = resolve;
    });
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(json({ code: "SESSION_INVALID" }, 401))
      .mockImplementationOnce(() => pending);
    render(<LoginPanel />);
    fireEvent.change(screen.getByLabelText("账号"), { target: { value: "customer_a" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "correct-horse" } });
    const button = screen.getByRole("button", { name: "进入对话" });
    await waitFor(() => expect(button).toBeEnabled());
    const form = button.closest("form");
    if (!form) {
      throw new Error("找不到登录表单");
    }
    fireEvent.submit(form);
    const busyButton = await screen.findByRole("button", { name: "进入对话中…" });
    expect(busyButton).toBeDisabled();
    resolveLogin(json(session));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/chat"));
  });
});
