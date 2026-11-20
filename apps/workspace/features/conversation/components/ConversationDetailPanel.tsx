"use client";

import { formatTime } from "@/lib/format";

import type { ConversationActionKind } from "../hooks/useConversationActions";
import { AUTHOR_LABEL } from "../labels";
import type { ConversationDetail } from "../types";

import { ConversationActions } from "./ConversationActions";

const STATUS_META: Record<string, { label: string; chip: string; dot: string }> = {
  AI_ACTIVE: {
    label: "AI 接待中",
    chip: "border-accent-line bg-accent-soft text-accent-ink",
    dot: "bg-success",
  },
  QUEUED: {
    label: "排队中",
    chip: "border-warning-line bg-warning-soft text-warning-ink",
    dot: "bg-warning",
  },
  CLAIMED: {
    label: "已领取，等待接管",
    chip: "border-warning-line bg-warning-soft text-warning-ink",
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

export type ConversationFeedback = {
  notice: string | null;
  error: string | null;
};

export type ConversationPanelActions = {
  /** 接管/登出等页面级动作进行中。 */
  busy: boolean;
  /** 关闭/转回动作进行中；与页面级 busy 分开，按钮各自给出文案。 */
  acting: ConversationActionKind | null;
  onTakeOver: () => void;
  onClose: () => void;
  onReturnToAi: () => void;
};

type ConversationDetailPanelProps = {
  detail: ConversationDetail;
  feedback: ConversationFeedback;
  actions: ConversationPanelActions;
};

const SECTION_TITLE = "m-0 text-xs font-medium text-text-3";

export function ConversationDetailPanel({
  detail,
  feedback,
  actions,
}: ConversationDetailPanelProps) {
  const { notice, error } = feedback;
  const meta = STATUS_META[detail.status] ?? {
    label: detail.status,
    chip: "border-border bg-surface-2 text-text-2",
    dot: "bg-text-3",
  };
  const handoff = detail.handoff;

  return (
    <div className="flex flex-col gap-5">
      <article className="overflow-hidden rounded-2xl border border-border bg-surface shadow-panel">
        <div className="flex flex-wrap items-center gap-3 border-b border-line-soft px-6 py-5 max-[767px]:px-4">
          <span
            aria-hidden="true"
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent-soft text-base font-medium text-accent-ink"
          >
            {detail.customer.display_name.slice(0, 1)}
          </span>
          <div className="min-w-0">
            <h2 className="m-0 text-base font-semibold">{detail.customer.display_name}</h2>
            <p className="mt-1 text-xs text-text-3">
              {detail.customer.username} · 会话 <code>{detail.id}</code>
            </p>
          </div>
          <span
            className={`ml-1 inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium ${meta.chip}`}
          >
            <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
            {meta.label}
          </span>

          <div className="ml-auto flex flex-wrap items-center gap-2 max-[767px]:ml-0">
            {detail.status === "CLAIMED" ? (
              <button
                className="h-9 rounded-lg border border-accent bg-accent px-4 text-sm font-medium text-white transition-colors hover:bg-accent/90 focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3"
                type="button"
                onClick={actions.onTakeOver}
                disabled={actions.busy}
              >
                {actions.busy ? "接管中…" : "接管会话"}
              </button>
            ) : null}
            {detail.status === "CLAIMED" || detail.status === "HUMAN_ACTIVE" ? (
              <ConversationActions
                busy={actions.acting}
                showReturn={detail.status === "HUMAN_ACTIVE"}
                onClose={actions.onClose}
                onReturnToAi={actions.onReturnToAi}
              />
            ) : null}
          </div>
        </div>

        <div className="px-6 py-5 max-[767px]:px-4">
          {error ? (
            <p
              className="mb-4 mt-0 rounded-xl border border-danger/15 bg-danger-soft px-3.5 py-2.5 text-sm text-danger"
              role="alert"
            >
              {error}
            </p>
          ) : null}
          {notice ? (
            <p
              className="mb-4 mt-0 rounded-xl border border-accent-line bg-accent-soft px-3.5 py-2.5 text-sm text-accent-ink"
              role="status"
            >
              {notice}
            </p>
          ) : null}

          <div className="grid gap-6 min-[1280px]:grid-cols-2">
            <section className="flex min-w-0 flex-col gap-2.5">
              <h3 className={SECTION_TITLE}>交接单</h3>
              {handoff ? (
                <>
                  <div className="rounded-xl border border-border bg-surface-2 px-3.5 py-3">
                    <p className="m-0 text-sm leading-relaxed text-text">
                      {handoff.summary || "（无摘要）"}
                    </p>
                  </div>
                  <dl className="grid grid-cols-2 gap-2">
                    <div className="rounded-xl border border-border bg-surface px-3 py-2.5">
                      <dt className="text-xs text-text-3">转人工原因</dt>
                      <dd className="mt-1 text-sm font-medium text-text">
                        {REASON_LABEL[handoff.reason] ?? handoff.reason}
                      </dd>
                    </div>
                    <div className="rounded-xl border border-border bg-surface px-3 py-2.5">
                      <dt className="text-xs text-text-3">订单</dt>
                      <dd className="mt-1 text-sm font-medium tabular-nums text-text">
                        {handoff.order_count}
                      </dd>
                    </div>
                    {handoff.failure_count != null ? (
                      <div className="col-span-2 rounded-xl border border-border bg-surface px-3 py-2.5">
                        <dt className="text-xs text-text-3">连续模型失败</dt>
                        <dd className="mt-1 text-sm font-medium text-text">
                          {handoff.failure_count} 次 · {handoff.last_error ?? "—"}
                        </dd>
                      </div>
                    ) : null}
                    <div className="col-span-2 rounded-xl border border-border bg-surface px-3 py-2.5">
                      <dt className="text-xs text-text-3">待办</dt>
                      {/* 待办是转人工时点的快照；交接单已结束时不再表示当前任务。 */}
                      <dd className="mt-1 text-sm font-medium text-text">
                        {handoff.status === "CLOSED" ? "—" : (handoff.pending_step ?? "—")}
                      </dd>
                    </div>
                  </dl>
                </>
              ) : (
                <p className="text-sm text-text-3">该会话暂无交接单。</p>
              )}
            </section>

            <section className="flex min-w-0 flex-col gap-2.5">
              <h3 className={SECTION_TITLE}>AI 轨迹</h3>
              {handoff && handoff.ai_trace.length > 0 ? (
                <ol className="m-0 flex list-none flex-col gap-1.5 p-0">
                  {handoff.ai_trace.map((event, index) => (
                    <li
                      key={`${event.created_at}-${index}`}
                      className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-2 px-3 py-2.5 text-xs"
                    >
                      <span className="min-w-0 truncate text-text">
                        {event.event_type} · {event.name}
                      </span>
                      <span className="shrink-0 tabular-nums text-text-3">
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
        </div>
      </article>

      <article className="rounded-2xl border border-border bg-surface px-6 py-5 shadow-panel max-[767px]:px-4">
        <h3 className={SECTION_TITLE}>转人工时最近消息（已脱敏）</h3>
        {handoff && handoff.messages.length > 0 ? (
          <ol className="m-0 mt-3 flex list-none flex-col gap-3 p-0" aria-live="polite">
            {handoff.messages.map((message) => (
              <li key={message.id} className="flex flex-col gap-1">
                <span className="text-xs text-text-3">
                  {AUTHOR_LABEL[message.author_type] ?? "系统"} ·{" "}
                  <time dateTime={message.created_at}>{formatTime(message.created_at)}</time>
                </span>
                <p className="m-0 w-fit max-w-[640px] whitespace-pre-wrap break-words rounded-xl bg-surface-2 px-3.5 py-2.5 text-sm leading-relaxed text-text">
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
