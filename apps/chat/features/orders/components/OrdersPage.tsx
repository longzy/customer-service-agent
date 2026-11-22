"use client";

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CircleAlert, Package } from "lucide-react";

import { Button } from "@/components/ui/Button";

import { useCancellation } from "../hooks/useCancellation";
import { useOrders } from "../hooks/useOrders";

import { CancelDialog } from "./CancelDialog";
import { OrderListItem } from "./OrderListItem";

const EMPTY_TITLE = "你名下暂时没有订单";
const EMPTY_HINT = "需要查询或转人工，可以回到聊天。";
const ERROR_TITLE = "订单加载失败";
const ERROR_HINT = "暂时无法获取订单，请稍后重试。";
const LOADING_TEXT = "正在加载订单";
const NULL_SEARCH = { get: () => null };

/**
 * 客户“我的订单”独立页面：最近 ≤5 笔订单。
 * 取消按钮与确认弹层复用同一任务接口；聊天卡片通过 `?cancel=` 进入同一弹层。
 */
export function OrdersPage() {
  const router = useRouter();
  const searchParams = useSearchParams() ?? NULL_SEARCH;
  const { state, retry, refresh } = useOrders();
  const {
    state: dialog,
    open,
    confirm,
    decline,
    refresh: refreshResult,
    close,
  } = useCancellation(() => void refresh());
  const handledParam = useRef<string | null>(null);
  const requested = searchParams.get("cancel");

  useEffect(() => {
    if (!requested || state.kind !== "ready" || handledParam.current === requested) {
      return;
    }
    handledParam.current = requested;
    const order = state.orders.find((item) => item.order_id === requested);
    // 参数只消费一次：刷新页面不再自动发起，避免重复创建任务。
    router.replace("/orders");
    if (order && (order.cancelable || order.cancellation?.can_confirm)) {
      void open(order);
    }
  }, [open, requested, router, state]);

  const backToChat = () => router.push("/chat");

  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-bg">
      <header className="flex h-16 shrink-0 items-center gap-3 border-b border-border bg-surface px-6 max-[1023px]:px-4">
        <Button variant="ghost" size="sm" onClick={backToChat}>
          返回聊天
        </Button>
        <h1 className="m-0 text-sm font-semibold">我的订单</h1>
        <span className="ml-auto text-xs text-text-3 max-[767px]:hidden">
          最近 5 笔，按下单时间倒序
        </span>
      </header>

      <div className="mx-auto w-full max-w-[860px] flex-1 overflow-y-auto px-6 py-6 max-[1023px]:px-4">
        {state.kind === "loading" ? (
          <div className="flex flex-col items-center gap-3 py-8" role="status">
            <span
              aria-hidden="true"
              className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-accent motion-reduce:animate-none"
            />
            <p className="m-0 text-sm text-text-2">{LOADING_TEXT}</p>
          </div>
        ) : state.kind === "error" ? (
          <div
            className="rounded-2xl border border-border bg-surface px-6 py-8 text-center"
            role="alert"
          >
            <span
              aria-hidden="true"
              className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-danger-soft text-danger"
            >
              <CircleAlert size={20} strokeWidth={1.6} />
            </span>
            <h2 className="mb-0 mt-3 text-lg font-semibold">{ERROR_TITLE}</h2>
            <p className="mb-0 mt-1.5 text-sm text-text-2">{ERROR_HINT}</p>
            <Button variant="primary" size="sm" className="mt-6" onClick={() => void retry()}>
              重试
            </Button>
          </div>
        ) : state.orders.length === 0 ? (
          <div className="rounded-2xl border border-border bg-surface px-6 py-8 text-center">
            <span
              aria-hidden="true"
              className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-surface-2 text-text-3"
            >
              <Package size={20} strokeWidth={1.6} />
            </span>
            <h2 className="mb-0 mt-3 text-lg font-semibold">{EMPTY_TITLE}</h2>
            <p className="mb-0 mt-1.5 text-sm text-text-2">{EMPTY_HINT}</p>
          </div>
        ) : (
          <section aria-labelledby="orders-heading">
            <h2 className="sr-only" id="orders-heading">
              最近订单
            </h2>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {state.orders.map((order) => (
                <li key={order.order_id}>
                  <OrderListItem order={order} onCancel={(item) => void open(item)} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <CancelDialog
        state={dialog}
        onConfirm={() => void confirm()}
        onDecline={() => void decline()}
        onRefresh={() => void refreshResult()}
        onClose={close}
      />
    </main>
  );
}
