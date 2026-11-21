"use client";

import { Avatar } from "@heroui/react";

import { Button } from "@/components/ui/Button";

import type { QueueItem } from "../types";

import { QueuePagination } from "./QueuePagination";

export const OVERDUE_SECONDS = 300;

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
  ORDER_QUERY_FAILURE: "订单查询失败",
};

type QueueTableProps = {
  items: QueueItem[];
  total: number;
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  selectedId: string | null;
  claimingId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onClaim: (item: QueueItem) => void;
};

export function formatWait(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${Math.floor(safe / 60)} 分 ${String(safe % 60).padStart(2, "0")} 秒`;
}

export function isOverdue(item: QueueItem): boolean {
  return item.waiting_seconds >= OVERDUE_SECONDS;
}

const TH =
  "sticky top-0 z-10 h-10 whitespace-nowrap border-b border-border bg-surface-muted px-3 text-left text-xs font-medium text-text-3";
const TD =
  "h-[60px] overflow-hidden text-ellipsis whitespace-nowrap border-b border-line-soft px-3 text-sm";

export function QueueTable({
  items,
  total,
  page,
  pageCount,
  onPageChange,
  selectedId,
  claimingId,
  disabled,
  onSelect,
  onClaim,
}: QueueTableProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-panel">
      <div className="min-h-0 flex-1 overflow-auto">
        <table
          aria-label="待接入队列"
          role="grid"
          className="w-full min-w-[760px] table-fixed border-collapse max-[767px]:min-w-0"
        >
          <colgroup>
            <col style={{ width: 180 }} />
            <col style={{ width: 96 }} />
            <col style={{ width: 140 }} className="max-[767px]:hidden" />
            <col className="max-[767px]:hidden" />
            <col style={{ width: 94 }} />
            <col style={{ width: 84 }} className="max-[767px]:hidden" />
          </colgroup>
          <thead>
            <tr>
              <th className={TH}>客户</th>
              <th className={TH}>等待</th>
              <th className={`${TH} max-[767px]:hidden`}>转人工原因</th>
              <th className={`${TH} max-[767px]:hidden`}>最后一条消息</th>
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
                  className={`cursor-pointer transition-colors last:[&>td]:border-0 hover:bg-surface-muted focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent ${selected ? "bg-surface-selected" : ""}`}
                  aria-selected={selected}
                  onClick={() => onSelect(item.handoff_id)}
                  onKeyDown={(event) => {
                    if (event.key === " ") {
                      event.preventDefault();
                      onSelect(item.handoff_id);
                    }
                  }}
                >
                  <td className={`${TD} ${selected ? "shadow-[inset_2px_0_0_var(--accent)]" : ""}`}>
                    <div className="flex items-center gap-2.5">
                      <Avatar className="h-8 w-8 shrink-0 bg-accent-soft text-xs font-medium text-accent-ink">
                        <Avatar.Fallback>{item.customer_display_name.slice(0, 1)}</Avatar.Fallback>
                      </Avatar>
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-text">
                          {item.customer_display_name}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-text-3">
                          {item.customer_username}
                        </span>
                      </span>
                    </div>
                  </td>
                  <td className={TD}>
                    {/* 等待只留时长数字，不再加轨道：轨道是数字的冗余编码，
                        满格后不提供区分度（2026-11-20 决策，ui-spec 3.7）。 */}
                    <div className="flex flex-col gap-1.5">
                      <span className="font-medium tabular-nums text-text">
                        {formatWait(item.waiting_seconds)}
                      </span>
                    </div>
                  </td>
                  <td className={`${TD} text-text-2 max-[767px]:hidden`}>
                    {REASON_LABEL[item.reason] ?? item.reason}
                  </td>
                  <td className={`${TD} text-text-3 max-[767px]:hidden`} title={item.last_message}>
                    {item.last_message || "（无客户消息）"}
                  </td>
                  <td className={TD}>
                    {/* 状态用圆点 + 文字，不用胶囊：颜色只作辅助（ui-spec 3.10）。 */}
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-text-2">
                      <span
                        aria-hidden="true"
                        className={`h-[7px] w-[7px] rounded-full ${overdue ? "bg-danger" : "bg-warning"}`}
                      />
                      {overdue ? "已超时" : "等待中"}
                    </span>
                  </td>
                  <td className={`${TD} text-right max-[767px]:hidden`}>
                    <Button
                      variant={selected ? "primary" : "secondary"}
                      size="sm"
                      disabled={disabled}
                      onClick={(event) => {
                        event.stopPropagation();
                        onClaim(item);
                      }}
                      aria-label={`领取 ${item.customer_display_name} 的会话`}
                    >
                      {claimingId === item.handoff_id ? "领取中" : "领取"}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex min-h-[44px] shrink-0 flex-wrap items-center gap-2.5 border-t border-line-soft bg-surface px-4 py-2 text-xs text-text-3">
        <span className="whitespace-nowrap">
          显示 <b className="font-medium text-text-2">{items.length}</b> / {total} 条
        </span>
        <span className="text-border-strong max-[1279px]:hidden">·</span>
        <span className="whitespace-nowrap max-[1279px]:hidden">
          队伍按创建时间升序（服务端 FIFO）
        </span>
        <span className="flex-1" />
        <QueuePagination page={page} pageCount={pageCount} onPageChange={onPageChange} />
      </div>
    </div>
  );
}
