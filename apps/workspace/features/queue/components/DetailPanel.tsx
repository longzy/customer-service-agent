"use client";

import type { QueueItem } from "../types";

import { DetailSections } from "./DetailSections";
import { formatWait, isOverdue } from "./QueueTable";

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
};

type DetailPanelProps = {
  item: QueueItem | null;
  open: boolean;
  claiming: boolean;
  disabled: boolean;
  onClaim: () => void;
  onClose: () => void;
};

const METRIC_LABEL = "block text-xs tracking-[0.04em] text-text-3";
const METRIC_VALUE = "mt-1 block text-sm font-semibold tabular-nums";

export function DetailPanel({
  item,
  open,
  claiming,
  disabled,
  onClaim,
  onClose,
}: DetailPanelProps) {
  return (
    <aside
      aria-label="会话详情"
      className={`flex min-h-screen w-[352px] shrink-0 flex-col gap-4 border-l border-border bg-surface px-[22px] py-5 max-[1279px]:w-[320px] max-[1023px]:fixed max-[1023px]:inset-y-0 max-[1023px]:right-0 max-[1023px]:z-20 max-[1023px]:min-h-0 max-[1023px]:overflow-y-auto max-[1023px]:shadow-[-24px_0_48px_-32px_rgba(19,33,28,0.4)] max-[1023px]:transition-transform ${
        open ? "max-[1023px]:translate-x-0" : "max-[1023px]:translate-x-full"
      }`}
    >
      <div className="flex items-center">
        <h2 className="m-0 text-sm font-semibold">会话详情</h2>
        <button
          className="ml-auto rounded-sm px-1.5 py-0.5 text-lg leading-none text-text-3 hover:text-text focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-default disabled:opacity-40"
          type="button"
          onClick={onClose}
          aria-label="关闭详情"
          disabled={!item}
        >
          ×
        </button>
      </div>

      {item ? (
        <>
          <div className="flex items-center gap-3">
            <span className="grid h-[42px] w-[42px] shrink-0 place-items-center rounded-full bg-avatar-strong-bg text-base text-avatar-strong-ink">
              {item.customer_display_name.slice(0, 1)}
            </span>
            <span>
              <span className="flex items-center gap-1.5 text-base font-semibold">
                {item.customer_display_name}
                <span className="inline-flex h-[18px] items-center rounded-full border border-border bg-bg px-2 text-xs font-normal text-text-2">
                  本租户
                </span>
              </span>
              <span className="mt-1 block text-xs tabular-nums text-text-3">
                {item.customer_username} · 会话 {item.conversation_id.slice(0, 8)}
              </span>
            </span>
          </div>

          <div className="grid grid-cols-[1fr_1.25fr_1fr] overflow-hidden rounded-lg border border-border">
            <div className="min-w-0 border-r border-border px-2.5 py-2.5">
              <span className={METRIC_LABEL}>等待</span>
              <span className={`${METRIC_VALUE} ${isOverdue(item) ? "text-danger" : ""}`}>
                {formatWait(item.waiting_seconds)}
              </span>
            </div>
            <div className="min-w-0 border-r border-border px-2.5 py-2.5">
              <span className={METRIC_LABEL}>转人工原因</span>
              <span className="mt-1 block text-xs leading-[1.4] text-text">
                {REASON_LABEL[item.reason] ?? item.reason}
              </span>
            </div>
            <div className="min-w-0 px-2.5 py-2.5">
              <span className={METRIC_LABEL}>订单</span>
              <span className={METRIC_VALUE}>{item.order_count}</span>
            </div>
          </div>

          <DetailSections item={item} />

          <div className="mt-auto flex flex-col gap-2">
            <button
              className="h-[38px] rounded-md border border-accent bg-accent text-sm font-medium text-surface hover:bg-brand-deep focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3"
              type="button"
              onClick={onClaim}
              disabled={disabled || claiming}
            >
              {claiming ? "领取中…" : "领取会话"}
            </button>
            <button
              className="h-[38px] rounded-md border border-border bg-surface text-sm text-text-3"
              type="button"
              disabled
              title="领取后进入会话页查看"
            >
              查看完整交接单
            </button>
            <p className="m-0 border-t border-line-soft pt-2.5 text-xs leading-[1.7] text-text-3">
              数据范围：本租户 · 仅坐席可见。超时阈值 5 分钟，超过后在列表中标记。
            </p>
          </div>
        </>
      ) : (
        <div className="grid flex-1 place-items-center p-6 text-center text-xs leading-[1.7] text-text-3">
          <p>选择左侧一行，查看客户与领取规则。</p>
        </div>
      )}
    </aside>
  );
}
