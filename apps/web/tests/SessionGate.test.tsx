import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionGate } from "@/components/SessionGate";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
}));

describe("SessionGate", () => {
  beforeEach(() => {
    replace.mockReset();
    vi.restoreAllMocks();
  });

  it("未登录时跳转登录页", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));
    render(<SessionGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("已登录时显示身份与退出", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          account_id: "zhang-ming",
          display_name: "张明",
          tenant_id: "tenant-a",
          tenant_name: "示例商户 A",
        }),
        { status: 200 },
      ),
    );
    render(<SessionGate />);
    expect(await screen.findByText("示例商户 A · 张明")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "退出" })).toBeInTheDocument();
  });
});
