import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatShell } from "@/components/ChatShell";

describe("ChatShell", () => {
  it("渲染空态标题与输入区", () => {
    render(<ChatShell />);

    expect(screen.getByRole("heading", { name: "客服中心" })).toBeInTheDocument();
    expect(screen.getByLabelText("输入消息")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送" })).toBeInTheDocument();
  });
});
