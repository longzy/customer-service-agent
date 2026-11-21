"use client";

import { useId } from "react";

import { formatAmount } from "@/lib/format";
import { orderStatusTone } from "@/lib/orderStatus";

import type { CustomerOrderSummary } from "../types";

type OrderListItemProps = {
  order: CustomerOrderSummary;
};

/**
 * “我的订单”列表项：只展示 OMS 白名单字段。
 * 取消按钮由 F-31 接入，本卡保持只读；article + tabIndex 让键盘/读屏可阅读。
 */
export function OrderListItem({ order }: OrderListItemProps) {
  const headingId = useId();
  const tone = orderStatusTone(order);

  return (
    <article
      aria-labelledby={headingId}
      className="rounded-2xl border border-border bg-surface p-4 focus-visible:shadow-focus focus-visible:outline-none"
      tabIndex={0}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3
          className="m-0 select-all font-mono text-xs font-medium tracking-tight text-text"
          id={headingId}
        >
          {order.order_id}
        </h3>
        <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-border px-2 text-xs">
          {/* 7px 与聊天订单卡片、ui-spec 3.16 的订单卡片契约一致，不按通用间距基数改写。 */}
          <span aria-hidden="true" className={`h-[7px] w-[7px] rounded-full ${tone.dot}`} />
          <span className={tone.text}>{order.status_label}</span>
        </span>
      </div>
      <p className="mb-0 mt-1.5 text-sm font-medium text-text">{order.item_summary}</p>
      <dl className="mb-0 mt-2 grid grid-cols-2 gap-1 text-xs">
        <div>
          <dt className="text-text-3">金额</dt>
          <dd className="m-0 mt-0.5 font-medium tabular-nums text-text">
            {formatAmount(order.amount_cents, order.currency)}
          </dd>
        </div>
        <div>
          <dt className="text-text-3">下单时间</dt>
          <dd className="m-0 mt-0.5 tabular-nums text-text">{order.created_at_local}</dd>
        </div>
      </dl>
    </article>
  );
}
