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
  {
    files: ["tests/**/*.{ts,tsx}"],
    rules: {
      // FE-TEST-06：mock 的 router 必须是模块级稳定引用。新对象会让依赖 router
      // 的 useCallback/useEffect 每次渲染重跑，同步渲染下会耗尽堆内存。
      "no-restricted-syntax": [
        "error",
        {
          selector: "Property[key.name='useRouter'] > ArrowFunctionExpression > ObjectExpression",
          message:
            "useRouter 的 mock 必须返回模块级稳定对象；改为 const router = { replace: vi.fn(), push: vi.fn() } 后 useRouter: () => router。",
        },
      ],
    },
  },
  globalIgnores([".next/**", "coverage/**", "next-env.d.ts"]),
]);
