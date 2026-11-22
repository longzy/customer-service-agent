import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": new URL("./", import.meta.url).pathname },
  },
  test: {
    environment: "jsdom",
    // forks 池按进程隔离；同时限制 worker 堆上限，让测试 mock 引起的同步死循环
    // 在 1–2 分钟内以 OOM 暴露，而不是在默认 4GB 堆下空转数分钟。
    pool: "forks",
    execArgv: ["--max-old-space-size=1536"],
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.tsx"],
  },
});
