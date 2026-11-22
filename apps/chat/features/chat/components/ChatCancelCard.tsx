"use client";

import { useId } from "react";

import { Button } from "@/components/ui/Button";
import { CANCEL_IMPACT_TEXT } from "@/lib/cancellationCopy";
import { formatAmount, formatDateTime } from "@/lib/format";
import { orderStatusTone } from "@/lib/orderStatus";

import type { CancellationSummary, OrderSummary } from "../types";

type ChatCancelCardProps = {
  order: OrderSummary;
  cancellation: CancellationSummary;
  onOpenOrders: (orderId: string) => void;
};

/**
 * 聊天内的取消确认卡片（AC-63）：与订单页弹层展示同一组事实与承诺。
 * 按钮只跳到订单页复用同一确认弹层，不在聊天里再实现一套确认状态机。
 */
export function ChatCancelCard({ order, cancellation, onOpenOrders }: ChatCancelCardProps) {
  const headingId = useId();
  const tone = orderStatusTone(order);

  return (
    <article
      aria-labelledby={headingId}
      className="w-full max-w-[560px] rounded-xl border border-warning-line bg-surface px-4 py-3 focus-visible:outline-none focus-visible:shadow-focus"
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
        <span className="inline-flex h-6 items-center rounded-full border border-warning-line bg-warning-soft px-2 text-xs text-warning-ink">
          尚未提交
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
          <dt className="text-text-3">确认有效期至</dt>
          <dd className="m-0 mt-0.5 tabular-nums text-text">
            {formatDateTime(cancellation.expires_at)}
          </dd>
        </div>
      </dl>
      <p className="mb-0 mt-2 text-xs leading-relaxed text-text-2">{CANCEL_IMPACT_TEXT}</p>
      <p className="mb-0 mt-2 text-xs leading-relaxed text-text-2">
        回复「确认取消」提交，或回复「不取消」放弃。
      </p>
      <div className="mt-3 flex justify-end">
        <Button variant="secondary" size="sm" onClick={() => onOpenOrders(order.order_id)}>
          去订单页确认
        </Button>
      </div>
    </article>
  );
}
