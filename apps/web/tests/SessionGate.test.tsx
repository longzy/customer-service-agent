import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionGate } from "@/components/SessionGate";

const replace = vi.fn();
const router = { push: vi.fn(), replace };

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

const session = {
  account_id: "zhang-ming",
  display_name: "张明",
  tenant_id: "tenant-a",
  tenant_name: "示例商户 A",
};

describe("SessionGate", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("未登录时跳转登录页（AC-20）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));
    render(<SessionGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("服务端错误不当作未登录，提示重试（AC-20）", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    );
    render(<SessionGate />);
    expect(await screen.findByRole("alert")).toHaveTextContent("请求未完成");
    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("已登录时显示身份，点击退出调用接口并跳转（AC-20）", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<SessionGate />);
    expect(await screen.findByText("示例商户 A · 张明")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "退出" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenLastCalledWith("/api/session", { method: "DELETE" });
  });

  it("退出失败时提示且不跳转（AC-20）", async () => {
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response("{}", { status: 500 }));
    render(<SessionGate />);
    fireEvent.click(await screen.findByRole("button", { name: "退出" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("退出失败");
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("SessionGate 重试", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("退出失败后点重试会再次调用退出（AC-20）", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response("{}", { status: 500 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<SessionGate />);
    fireEvent.click(await screen.findByRole("button", { name: "退出" }));
    fireEvent.click(await screen.findByRole("button", { name: "重试" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/session", { method: "DELETE" });
  });
});
