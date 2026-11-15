import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPanel } from "@/components/LoginPanel";

const push = vi.fn();
const router = { push, replace: vi.fn() };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

const accounts = [
  {
    account_id: "zhang-ming",
    display_name: "张明",
    tenant_id: "tenant-a",
    tenant_name: "示例商户 A",
  },
  {
    account_id: "wang-qiang",
    display_name: "王强",
    tenant_id: "tenant-b",
    tenant_name: "示例商户 B",
  },
];

describe("LoginPanel", () => {
  beforeEach(() => {
    push.mockReset();
    vi.restoreAllMocks();
  });

  it("拉取账号并默认选中第一个（AC-20）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify(accounts), { status: 200 }),
    );
    render(<LoginPanel />);
    expect(await screen.findByText("张明")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /以张明身份进入/ })).toBeInTheDocument();
  });

  it("选择账号后登录并跳转（AC-20）", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(accounts), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(accounts[1]), { status: 200 }));
    render(<LoginPanel />);
    fireEvent.click(await screen.findByText("王强"));
    fireEvent.click(screen.getByRole("button", { name: /以王强身份进入/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/"));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/session",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ account_id: "wang-qiang" }),
      }),
    );
  });

  it("账号拉取失败时显示错误（AC-20）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "服务不可用" }), { status: 503 }),
    );
    render(<LoginPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("服务不可用");
  });
});

it("空账号列表时提示无可用账号（AC-20）", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(new Response("[]", { status: 200 }));
  render(<LoginPanel />);
  expect(await screen.findByText("无可用账号")).toBeInTheDocument();
});
