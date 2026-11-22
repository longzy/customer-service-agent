"use client";

import { useId } from "react";

import { Button } from "@/components/ui/Button";
import { CANCEL_IMPACT_TEXT } from "@/lib/cancellationCopy";
import { formatAmount, formatDateTime } from "@/lib/format";
import { isCancelable, orderStatusTone } from "@/lib/orderStatus";

import type { CancellationSummary, OrderSummary } from "../types";

type OrderCardProps = {
  order: OrderSummary;
  onCancel: (orderId: string) => void;
  /** 有待确认的取消任务时切换为确认卡片（F-32）；未传时保持普通订单卡片。 */
  cancellation?: CancellationSummary | null;
};

/**
 * 聊天里的订单卡片：只展示 OMS 快照白名单字段。
 * article + tabIndex 让键盘/读屏用户可以停在卡片上完整阅读；
 * 有待确认任务时同一张卡片承担确认卡片职责，避免两套订单事实展示。
 */
export function OrderCard({ order, onCancel, cancellation = null }: OrderCardProps) {
  const headingId = useId();
  const tone = orderStatusTone(order);
  const pending = cancellation?.can_confirm ? cancellation : null;

  return (
    <article
      aria-labelledby={headingId}
      className={`w-full rounded-xl border bg-surface px-4 py-3 focus-visible:outline-none focus-visible:shadow-focus ${
        pending ? "border-warning-line" : "border-border"
      }`}
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
        {pending ? (
          <span className="inline-flex h-6 items-center rounded-full border border-warning-line bg-warning-soft px-2 text-xs text-warning-ink">
            尚未提交
          </span>
        ) : null}
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
          <dt className="text-text-3">{pending ? "确认有效期至" : "下单时间"}</dt>
          <dd className="m-0 mt-0.5 tabular-nums text-text">
            {pending ? formatDateTime(pending.expires_at) : order.created_at_local}
          </dd>
        </div>
      </dl>
      {pending ? (
        <>
          <p className="mb-0 mt-2 text-xs leading-relaxed text-text-2">{CANCEL_IMPACT_TEXT}</p>
          <p className="mb-0 mt-2 text-xs leading-relaxed text-text-2">
            回复「确认取消」提交，或回复「不取消」放弃。
          </p>
        </>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-2">
        <p className="mb-0 text-[11px] leading-none text-text-3">查询时状态</p>
        {pending || isCancelable(order.order_status) ? (
          <Button variant="secondary" size="sm" onClick={() => onCancel(order.order_id)}>
            {pending ? "去订单页确认" : "取消订单"}
          </Button>
        ) : null}
      </div>
    </article>
  );
}
