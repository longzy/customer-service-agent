"use client";

import { formatTime } from "@/lib/format";

import type { ConversationDetail } from "../types";

const STATUS_META: Record<string, { label: string; chip: string; dot: string }> = {
  AI_ACTIVE: {
    label: "AI 接待中",
    chip: "border-accent-line bg-accent-soft text-accent-ink",
    dot: "bg-success",
  },
  QUEUED: {
    label: "排队中",
    chip: "border-warning-line bg-warning-soft text-warning",
    dot: "bg-warning",
  },
  CLAIMED: {
    label: "已领取，等待接管",
    chip: "border-warning-line bg-warning-soft text-warning",
    dot: "bg-warning",
  },
  HUMAN_ACTIVE: {
    label: "人工接入中",
    chip: "border-accent-line bg-accent-soft text-accent-ink",
    dot: "bg-success",
  },
  CLOSED: {
    label: "已结束",
    chip: "border-border bg-surface-2 text-text-2",
    dot: "bg-text-3",
  },
};

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
};

const AUTHOR_LABEL: Record<string, string> = {
  customer: "客户",
  ai: "客服 AI",
  agent: "坐席",
  system: "系统",
};

type ConversationDetailPanelProps = {
  detail: ConversationDetail;
  busy: boolean;
  notice: string | null;
  error: string | null;
  onTakeOver: () => void;
};

export function ConversationDetailPanel({
  detail,
  busy,
  notice,
  error,
  onTakeOver,
}: ConversationDetailPanelProps) {
  const meta = STATUS_META[detail.status] ?? {
    label: detail.status,
    chip: "border-border bg-surface-2 text-text-2",
    dot: "bg-text-3",
  };
  const handoff = detail.handoff;

  return (
    <div className="flex flex-col gap-4">
      <article className="rounded-xl border border-border bg-surface px-5 py-5">
        <div className="flex flex-wrap items-center gap-3">
          <span
            aria-hidden="true"
            className="grid h-[42px] w-[42px] place-items-center rounded-full bg-avatar-strong-bg text-base text-avatar-strong-ink"
          >
            {detail.customer.display_name.slice(0, 1)}
          </span>
          <div className="min-w-0">
            <h2 className="m-0 text-base font-semibold">{detail.customer.display_name}</h2>
            <p className="mt-1 text-xs tabular-nums text-text-3">
              {detail.customer.username} · 会话 <code>{detail.id}</code>
            </p>
          </div>
          <span
            className={`ml-auto inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium ${meta.chip}`}
          >
            <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
            {meta.label}
          </span>
          {detail.status === "CLAIMED" ? (
            <button
              className="h-[34px] rounded-md border border-accent bg-accent px-3.5 text-sm font-medium text-surface hover:bg-brand-deep focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3"
              type="button"
              onClick={onTakeOver}
              disabled={busy}
            >
              {busy ? "接管中…" : "接管会话"}
            </button>
          ) : null}
        </div>

        {error ? (
          <p
            className="mt-3.5 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger"
            role="alert"
          >
            {error}
          </p>
        ) : null}
        {notice ? (
          <p
            className="mt-3.5 rounded-md bg-accent-soft px-3 py-2 text-sm text-accent-ink"
            role="status"
          >
            {notice}
          </p>
        ) : null}

        <div className="mt-5 grid gap-4 min-[1280px]:grid-cols-2">
          <section className="flex flex-col gap-2">
            <h3 className="m-0 text-xs font-semibold tracking-[0.06em] text-text-2">交接单</h3>
            {handoff ? (
              <>
                <div className="rounded-[9px] border border-line-soft bg-surface-soft px-3 py-2.5">
                  <p className="m-0 text-sm leading-[1.7] text-text">
                    {handoff.summary || "（无摘要）"}
                  </p>
                </div>
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-[9px] border border-line-soft px-3 py-2">
                    <dt className="text-text-3">转人工原因</dt>
                    <dd className="mt-1 font-medium text-text">
                      {REASON_LABEL[handoff.reason] ?? handoff.reason}
                    </dd>
                  </div>
                  <div className="rounded-[9px] border border-line-soft px-3 py-2">
                    <dt className="text-text-3">订单</dt>
                    <dd className="mt-1 font-medium tabular-nums text-text">
                      {handoff.order_count}
                    </dd>
                  </div>
                  <div className="col-span-2 rounded-[9px] border border-line-soft px-3 py-2">
                    <dt className="text-text-3">待办</dt>
                    <dd className="mt-1 font-medium text-text">{handoff.pending_step ?? "—"}</dd>
                  </div>
                </dl>
              </>
            ) : (
              <p className="text-sm text-text-3">该会话暂无交接单。</p>
            )}
          </section>

          <section className="flex flex-col gap-2">
            <h3 className="m-0 text-xs font-semibold tracking-[0.06em] text-text-2">AI 轨迹</h3>
            {handoff && handoff.ai_trace.length > 0 ? (
              <ol className="m-0 flex list-none flex-col gap-1.5 p-0">
                {handoff.ai_trace.map((event, index) => (
                  <li
                    key={`${event.created_at}-${index}`}
                    className="flex items-center justify-between rounded-[9px] border border-line-soft bg-surface-soft px-3 py-2 text-xs"
                  >
                    <span className="text-text">
                      {event.event_type} · {event.name}
                    </span>
                    <span className="tabular-nums text-text-3">
                      {event.status}
                      {event.confidence === null ? "" : ` · ${event.confidence.toFixed(2)}`}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-text-3">暂无 AI 事件。</p>
            )}
          </section>
        </div>
      </article>

      <article className="rounded-xl border border-border bg-surface px-5 py-5">
        <h3 className="m-0 text-xs font-semibold tracking-[0.06em] text-text-2">
          转人工时最近消息（已脱敏）
        </h3>
        {handoff && handoff.messages.length > 0 ? (
          <ol className="m-0 mt-3 flex list-none flex-col gap-2.5 p-0" aria-live="polite">
            {handoff.messages.map((message) => (
              <li key={message.id} className="flex flex-col gap-1">
                <span className="text-xs text-text-3">
                  {AUTHOR_LABEL[message.author_type] ?? "系统"} ·{" "}
                  <time dateTime={message.created_at}>{formatTime(message.created_at)}</time>
                </span>
                <p className="m-0 w-fit max-w-[640px] whitespace-pre-wrap break-words rounded-xl bg-surface-2 px-3.5 py-2.5 text-sm leading-[1.7] text-text">
                  {message.content}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-3 text-sm text-text-3">暂无消息。</p>
        )}
      </article>
    </div>
  );
}
