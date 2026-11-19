"use client";

import { useEffect, useRef } from "react";

import type { Message, MessageAuthor } from "../types";

const AUTHOR_LABELS: Record<MessageAuthor, string> = {
  customer: "客户",
  ai: "客服 AI",
  agent: "坐席",
  system: "系统",
};

const QUICK_ACTIONS = [
  {
    label: "查订单",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M3 4.5h10M3 8h10M3 11.5h6"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    label: "改地址",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M8 2.5l5 4.5v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7l5-4.5Z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    label: "转人工",
    icon: (
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M3 4.5A2.5 2.5 0 0 1 5.5 2h5A2.5 2.5 0 0 1 13 4.5v4a2.5 2.5 0 0 1-2.5 2.5H7l-3 2.5V11A2.5 2.5 0 0 1 3 8.5v-4Z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
];

type MessageListProps = {
  messages: Message[];
  loading: boolean;
  status: string;
  onQuick: (text: string) => void;
};

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function authorLabel(authorType: MessageAuthor): string {
  return AUTHOR_LABELS[authorType] ?? "系统";
}

const BUBBLE_BASE =
  "rounded-xl px-3.5 py-2.5 text-base leading-[1.7] whitespace-pre-wrap break-words";

export function MessageList({ messages, loading, status, onQuick }: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = listRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages.length, loading, status]);

  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-[18px] overflow-y-auto px-8 pb-3 pt-[26px] max-[1023px]:px-4 max-[1023px]:py-4"
      ref={listRef}
      role="log"
      aria-live="polite"
      aria-label="消息记录"
    >
      {loading ? (
        <div className="flex flex-col gap-2.5 py-1.5" aria-label="加载中">
          <span className="block h-11 w-[62%] animate-pulse motion-reduce:animate-none rounded-xl bg-surface-muted" />
          <span className="block h-11 w-[48%] animate-pulse motion-reduce:animate-none self-end rounded-xl bg-surface-muted" />
          <span className="block h-11 w-[70%] animate-pulse motion-reduce:animate-none rounded-xl bg-surface-muted" />
        </div>
      ) : null}

      {!loading ? (
        <div className="max-w-[640px] rounded-xl border border-sand-line bg-sand p-[18px]">
          <h2 className="m-0 font-serif text-[20px] font-semibold tracking-[0.01em]">
            你好，我是小回。
          </h2>
          <p className="mb-0 mt-2 max-w-[520px] text-base leading-[1.75] text-text-2">
            我可以帮你查订单、改配送、办理退换。需要真人时，直接说「转人工」。
          </p>
          <div className="mt-3.5 grid grid-cols-3 gap-2 min-[768px]:max-[1023px]:grid-cols-1 max-[767px]:grid-cols-2">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.label}
                type="button"
                className="flex items-center gap-2 rounded-[11px] border border-border bg-surface px-2.5 py-2 text-left text-sm text-text hover:border-border-strong focus-visible:outline-none focus-visible:shadow-focus"
                onClick={() => onQuick(action.label)}
              >
                <span className="text-accent">{action.icon}</span>
                {action.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {messages.map((message) => {
        const author = message.author_type;
        const isCustomer = author === "customer";
        const isSystem = author === "system";

        if (isSystem) {
          return (
            <p key={message.id} className="m-0 self-center text-center text-xs text-text-3">
              {message.content}
            </p>
          );
        }

        const tone = isCustomer
          ? "bg-brand-deep text-paper rounded-tr-[4px]"
          : author === "agent"
            ? "border border-accent-line bg-accent-soft text-accent-ink rounded-tl-[4px]"
            : "border border-border bg-surface rounded-tl-[4px]";

        return (
          <article
            key={message.id}
            className={`flex max-w-[560px] gap-2.5 ${isCustomer ? "justify-end self-end" : "items-start"}`}
            data-author={author}
          >
            {!isCustomer ? (
              <span
                aria-hidden="true"
                className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-[9px] bg-brand-deep font-serif text-base text-presence-ink"
              >
                {author === "agent" ? "座" : "回"}
              </span>
            ) : null}
            <div className="flex min-w-0 flex-col gap-1">
              <span className="sr-only">{authorLabel(author)}</span>
              <div className={`${BUBBLE_BASE} ${tone}`}>{message.content}</div>
            </div>
            <time
              className="mb-0.5 shrink-0 self-end text-xs tabular-nums text-text-3"
              dateTime={message.created_at}
            >
              {formatTime(message.created_at)}
            </time>
          </article>
        );
      })}

      {status === "QUEUED" ? (
        <div
          className="flex max-w-[640px] items-start gap-3 rounded-xl border border-warning-line bg-warning-soft px-4 py-3"
          role="status"
        >
          <span
            aria-hidden="true"
            className="mt-1 h-[9px] w-[9px] shrink-0 animate-pulse motion-reduce:animate-none rounded-full bg-warning shadow-[0_0_0_5px_var(--halo-warning)]"
          />
          <div>
            <div className="text-sm font-semibold text-warning-ink">正在为你接通人工客服</div>
            <div className="mt-1 text-xs leading-[1.65] text-warning-ink">
              接通后会在这里提示你，也可以先补充问题。
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
