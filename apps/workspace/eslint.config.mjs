import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // 存量页面在 effect 内一次性拉数据并 setState（gate 模式）；React Compiler
      // 的新规则会把它当反模式。迁到数据获取层后删除本例外。
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores([".next/**", "coverage/**", "next-env.d.ts"]),
]);
