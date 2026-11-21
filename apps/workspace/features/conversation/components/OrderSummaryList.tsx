"use client";

import { useId } from "react";

import type { ConversationDetail } from "../types";

import { OrderSummaryCard } from "./OrderSummaryCard";

type Handoff = NonNullable<ConversationDetail["handoff"]>;
type OrderContextStatus = Handoff["order_context_status"];
type OrderSummary = NonNullable<Handoff["orders"]>[number];

const SECTION_TITLE = "m-0 text-xs font-medium text-text-3";

const EMPTY_TEXT = "该客户名下暂无订单";
const FAILED_TEXT = "订单信息暂不可用";
const UNKNOWN_TEXT = "该会话未查询订单";

type OrderSummaryListProps = {
  orders: OrderSummary[];
  status: OrderContextStatus;
};

function statusText(status: OrderContextStatus): string {
  if (status === "failed") {
    return FAILED_TEXT;
  }
  if (status === "unknown") {
    return UNKNOWN_TEXT;
  }
  return EMPTY_TEXT;
}

/**
 * 坐席会话详情的“最近订单”区：数据来自交接单快照，不实时查 OMS。
 * `empty` 与 `unknown` 必须分开说，避免把“没查”读成“客户没有订单”。
 */
export function OrderSummaryList({ orders, status }: OrderSummaryListProps) {
  const titleId = useId();
  const hasOrders = status === "ok" && orders.length > 0;

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-2.5">
      <h3 className={SECTION_TITLE} id={titleId}>
        最近订单
      </h3>
      {hasOrders ? (
        <ul aria-label="客户最近订单" className="m-0 flex list-none flex-col gap-2 p-0">
          {orders.map((order) => (
            <li key={order.order_id}>
              <OrderSummaryCard order={order} />
            </li>
          ))}
        </ul>
      ) : (
        <p
          className="m-0 rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 text-sm text-text-3"
          role="status"
        >
          {statusText(status)}
        </p>
      )}
      <p className="m-0 text-[11px] text-text-3">订单为转人工时的快照，可能已更新。</p>
    </section>
  );
}
