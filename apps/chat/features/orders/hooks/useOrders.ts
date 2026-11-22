"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api-client";

import { getOrders } from "../api/orders";
import type { CustomerOrderSummary } from "../types";

/** 列表页三态；错误态不伪装成空态（ui-spec 3.11）。 */
export type OrdersState =
  { kind: "loading" } | { kind: "error" } | { kind: "ready"; orders: CustomerOrderSummary[] };

/**
 * 订单列表的读取与重试；401 只由后端判定，收到后统一回登录页。
 * 列表是只读接口，重复进入页面即重新拉取，不做客户端缓存。
 */
export function useOrders() {
  const router = useRouter();
  const [state, setState] = useState<OrdersState>({ kind: "loading" });

  const load = useCallback(
    async (silent = false) => {
      if (!silent) {
        setState({ kind: "loading" });
      }
      try {
        const page = await getOrders();
        setState({ kind: "ready", orders: page.orders });
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 401) {
          router.replace("/login");
          return;
        }
        // FE-DATA-03：界面只展示兜底文案，不直出后端 message。
        setState({ kind: "error" });
      }
    },
    [router],
  );

  useEffect(() => {
    void load();
  }, [load]);

  return {
    state,
    retry: useCallback(() => load(), [load]),
    // 取消后刷新列表但不闪加载态，弹层保持打开直到用户关闭。
    refresh: useCallback(() => load(true), [load]),
  };
}
