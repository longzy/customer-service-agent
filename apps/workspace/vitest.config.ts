import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": new URL("./", import.meta.url).pathname },
  },
  test: {
    environment: "jsdom",
    // HeroUI/React 19 在 threads 池里全量跑会卡住事件循环（单个文件正常，
    // 全量各文件首个异步用例挂起到 runner 超时）；forks 池按进程隔离稳定。
    pool: "forks",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["tests/**/*.test.tsx"],
  },
});
