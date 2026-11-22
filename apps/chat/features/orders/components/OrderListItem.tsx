"use client";

import { useId } from "react";

import { Button } from "@/components/ui/Button";
import { formatAmount } from "@/lib/format";
import { orderStatusTone } from "@/lib/orderStatus";

import type { CustomerOrderSummary } from "../types";

type OrderListItemProps = {
  order: CustomerOrderSummary;
  onCancel: (order: CustomerOrderSummary) => void;
};

/**
 * “我的订单”列表项：只展示 OMS 白名单字段。
 * 取消按钮只做入口，资格与提交都由服务端重新判定；有进行中任务时停在
 * “待确认/已受理”状态，避免重复发起（design 3.3）。
 */
export function OrderListItem({ order, onCancel }: OrderListItemProps) {
  const headingId = useId();
  const tone = orderStatusTone(order);
  const cancellation = order.cancellation;

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
      {cancellation ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
          <p className="m-0 text-xs text-text-2">{cancellation.status_text}</p>
          {cancellation.can_confirm ? (
            <Button variant="soft" size="sm" onClick={() => onCancel(order)}>
              去确认
            </Button>
          ) : null}
        </div>
      ) : order.cancelable ? (
        <div className="mt-3 flex justify-end border-t border-border pt-3">
          <Button variant="secondary" size="sm" onClick={() => onCancel(order)}>
            取消订单
          </Button>
        </div>
      ) : null}
    </article>
  );
}
