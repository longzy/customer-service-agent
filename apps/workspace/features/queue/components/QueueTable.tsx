"use client";

import type { QueueItem } from "../types";

export const OVERDUE_SECONDS = 300;

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
};

type QueueTableProps = {
  items: QueueItem[];
  total: number;
  selectedId: string | null;
  claimingId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onClaim: (item: QueueItem) => void;
};

export function formatWait(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

export function isOverdue(item: QueueItem): boolean {
  return item.waiting_seconds >= OVERDUE_SECONDS;
}

const TH =
  "h-[38px] whitespace-nowrap border-b border-border bg-surface-muted px-2.5 text-left text-xs font-semibold tracking-[0.02em] text-text-2";
const TD =
  "h-14 overflow-hidden text-ellipsis whitespace-nowrap border-b border-line-soft px-2.5 text-sm";
const CLAIM =
  "h-7 rounded-[7px] border border-border bg-surface px-2.5 text-xs text-text hover:border-border-strong focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-text-3";
const CLAIM_PRIMARY =
  "h-7 rounded-[7px] border border-accent bg-accent px-2.5 text-xs text-surface hover:bg-brand-deep focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-text-3";

export function QueueTable({
  items,
  total,
  selectedId,
  claimingId,
  disabled,
  onSelect,
  onClaim,
}: QueueTableProps) {
  return (
    <div className="mt-3.5 overflow-x-auto rounded-xl border border-border bg-surface">
      <table
        aria-label="待接入队列"
        role="grid"
        className="w-full min-w-[760px] table-fixed border-collapse"
      >
        <colgroup>
          <col style={{ width: 40 }} />
          <col style={{ width: 168 }} />
          <col style={{ width: 70 }} />
          <col style={{ width: 122 }} />
          <col />
          <col style={{ width: 50 }} />
          <col style={{ width: 78 }} />
          <col style={{ width: 76 }} />
        </colgroup>
        <thead>
          <tr>
            <th className={TH}>
              <input
                type="checkbox"
                disabled
                aria-label="批量选择（暂不可用）"
                className="block h-[15px] w-[15px] appearance-none rounded-sm border-[1.5px] border-border-strong bg-surface opacity-60"
              />
            </th>
            <th className={TH}>客户</th>
            <th className={TH}>等待</th>
            <th className={`${TH} max-[1023px]:hidden`}>转人工原因</th>
            <th className={TH}>最后一条消息</th>
            <th className={`${TH} text-right max-[1024px]:hidden`}>订单</th>
            <th className={TH}>状态</th>
            <th className={`${TH} text-right max-[767px]:hidden`}>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const overdue = isOverdue(item);
            const selected = item.handoff_id === selectedId;
            return (
              <tr
                key={item.handoff_id}
                tabIndex={0}
                className={`cursor-pointer hover:bg-surface-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent ${selected ? "bg-surface-selected" : ""}`}
                aria-selected={selected}
                onClick={() => onSelect(item.handoff_id)}
                onKeyDown={(event) => {
                  if (event.key === " ") {
                    event.preventDefault();
                    onSelect(item.handoff_id);
                  }
                }}
              >
                <td className={`${TD} ${selected ? "shadow-[inset_3px_0_0_var(--accent)]" : ""}`}>
                  <input
                    type="checkbox"
                    disabled
                    aria-label={`选择 ${item.customer_display_name}`}
                    className="block h-[15px] w-[15px] appearance-none rounded-sm border-[1.5px] border-border-strong bg-surface opacity-60"
                  />
                </td>
                <td className={TD}>
                  <div className="flex items-center gap-2.5">
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-avatar-bg text-xs text-avatar-ink">
                      {item.customer_display_name.slice(0, 1)}
                    </span>
                    <span>
                      <span className="block font-medium text-text">
                        {item.customer_display_name}
                      </span>
                      <span className="block text-xs tabular-nums text-text-3">
                        {item.customer_username}
                      </span>
                    </span>
                  </div>
                </td>
                <td className={TD}>
                  <span
                    className={`font-medium tabular-nums ${overdue ? "text-danger" : "text-text"}`}
                  >
                    {formatWait(item.waiting_seconds)}
                  </span>
                </td>
                <td className={`${TD} text-text-2 max-[1023px]:hidden`}>
                  {REASON_LABEL[item.reason] ?? item.reason}
                </td>
                <td className={`${TD} text-text-2`}>{item.last_message || "（无客户消息）"}</td>
                <td className={`${TD} text-right tabular-nums text-text-2 max-[1024px]:hidden`}>
                  {item.order_count}
                </td>
                <td className={TD}>
                  <span
                    className={`inline-flex items-center gap-1.5 text-xs ${overdue ? "text-danger" : "text-text-2"}`}
                  >
                    <span
                      aria-hidden="true"
                      className={`h-[7px] w-[7px] rounded-full ${overdue ? "bg-danger" : "bg-warning"}`}
                    />
                    {overdue ? "已超时" : "等待中"}
                  </span>
                </td>
                <td className={`${TD} text-right max-[767px]:hidden`}>
                  <button
                    type="button"
                    className={selected ? CLAIM_PRIMARY : CLAIM}
                    disabled={disabled}
                    onClick={(event) => {
                      event.stopPropagation();
                      onClaim(item);
                    }}
                    aria-label={`领取 ${item.customer_display_name} 的会话`}
                  >
                    {claimingId === item.handoff_id ? "领取中" : "领取"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="flex h-[38px] items-center gap-2.5 border-t border-line-soft bg-surface-quiet px-3 text-xs text-text-3">
        <span>
          显示 <b className="font-medium text-text-2">{items.length}</b> / {total} 条
        </span>
        <span className="text-border-strong">·</span>
        <span>队伍按创建时间升序（服务端 FIFO）</span>
        <span className="flex-1" />
        <span>领取冲突会刷新队列并提示</span>
      </div>
    </div>
  );
}
