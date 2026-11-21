"use client";

import { useId } from "react";

import { formatAmount } from "@/lib/format";

import type { OrderSummary } from "../lib/orderStatus";
import { orderStatusTone } from "../lib/orderStatus";

type OrderCardProps = {
  order: OrderSummary;
};

/**
 * 聊天里的单笔订单卡片：只展示 OMS 快照白名单字段。
 * article + tabIndex 让键盘/读屏用户可以停在卡片上完整阅读；
 * 页脚标注“查询时状态”，提醒快照可能已变化。
 */
export function OrderCard({ order }: OrderCardProps) {
  const headingId = useId();
  const tone = orderStatusTone(order);

  return (
    <article
      aria-labelledby={headingId}
      className="w-full rounded-xl border border-border bg-surface px-4 py-3 focus-visible:outline-none focus-visible:shadow-focus"
      tabIndex={0}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4
          className="m-0 select-all font-mono text-xs font-medium tracking-tight text-text"
          id={headingId}
        >
          {order.order_id}
        </h4>
        <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-border px-2 text-xs">
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
      <p className="mb-0 mt-2 text-[11px] leading-none text-text-3">查询时状态</p>
    </article>
  );
}
