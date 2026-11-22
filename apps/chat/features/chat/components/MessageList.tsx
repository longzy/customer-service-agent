"use client";

import { useEffect, useRef } from "react";
import { House, List, MessageCircle } from "lucide-react";

import { EchoWaves } from "@/components/ui/EchoWaves";

import type { Message, MessageAuthor } from "../types";

import { OrderCard } from "./OrderCard";

const AUTHOR_LABELS: Record<MessageAuthor, string> = {
  customer: "客户",
  ai: "客服 AI",
  agent: "坐席",
  system: "系统",
};

const QUICK_ACTIONS = [
  {
    label: "查订单",
    icon: <List size={15} strokeWidth={1.6} aria-hidden="true" />,
  },
  {
    label: "改地址",
    icon: <House size={15} strokeWidth={1.6} aria-hidden="true" />,
  },
  {
    label: "转人工",
    icon: <MessageCircle size={15} strokeWidth={1.6} aria-hidden="true" />,
  },
];

type MessageListProps = {
  messages: Message[];
  loading: boolean;
  status: string;
  onQuick: (text: string) => void;
  onCancelOrder: (orderId: string) => void;
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
  "max-w-[min(560px,100%)] rounded-2xl px-4 py-2.5 text-base leading-[1.65] whitespace-pre-wrap break-words";

const AVATAR = "grid h-8 w-8 shrink-0 place-items-center rounded-full text-xs font-semibold";

export function MessageList({
  messages,
  loading,
  status,
  onQuick,
  onCancelOrder,
}: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = listRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages.length, loading, status]);

  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto py-7 max-[1023px]:py-5"
      ref={listRef}
      role="log"
      aria-live="polite"
      aria-label="消息记录"
    >
      {loading ? (
        <div className="flex flex-col gap-3" aria-label="加载中">
          <span className="block h-16 w-[70%] animate-pulse motion-reduce:animate-none rounded-2xl bg-surface-2" />
          <span className="block h-10 w-[46%] animate-pulse motion-reduce:animate-none self-end rounded-2xl bg-surface-2" />
          <span className="block h-12 w-[58%] animate-pulse motion-reduce:animate-none rounded-2xl bg-surface-2" />
        </div>
      ) : null}

      {!loading ? (
        <section className="relative max-w-[560px] self-start overflow-hidden rounded-2xl border border-border bg-surface p-4 shadow-panel">
          {/* 品牌回声只在这一张欢迎卡上出现一次，进入对话后不再出现（ui-spec 2.7）。 */}
          <div className="pointer-events-none absolute -bottom-10 -right-12 h-[170px] w-[170px] text-text opacity-70">
            <EchoWaves className="h-full w-full" />
          </div>
          <div className="relative">
            <h2 className="m-0 text-base font-semibold tracking-[-0.01em]">你好，我是小回。</h2>
            <p className="mb-0 mt-1 text-sm leading-relaxed text-text-2">
              我可以帮你查订单、改配送、办理退换。需要真人时，直接说「转人工」。
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border bg-surface px-3 text-xs text-text-2 transition-colors hover:border-accent-line hover:bg-accent-soft hover:text-accent-ink focus-visible:outline-none focus-visible:shadow-focus"
                  onClick={() => onQuick(action.label)}
                >
                  <span className="text-accent">{action.icon}</span>
                  {action.label}
                </button>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {messages.map((message) => {
        const author = message.author_type;
        const isCustomer = author === "customer";
        const isSystem = author === "system";
        // F-32：有待确认任务时同一张订单卡片切换为确认态（OrderCard 的 cancellation）。
        const cancellation = message.payload?.cancellation;

        if (isSystem) {
          return (
            <p
              key={message.id}
              className="m-0 self-center rounded-full bg-surface-2 px-3 py-1 text-xs text-text-3"
            >
              {message.content}
            </p>
          );
        }

        // 客户黑底、AI/坐席白底：近黑主题下强调色浅底与表面色过于接近，
        // 非客户消息统一白底 + 描边，用头像与作者标签区分 AI 与坐席。
        const tone = isCustomer
          ? "bg-accent text-white"
          : "border border-border bg-surface text-text";

        return (
          <article
            key={message.id}
            className={`flex w-full max-w-[640px] gap-2.5 ${isCustomer ? "justify-end self-end" : "items-start"}`}
            data-author={author}
          >
            {!isCustomer ? (
              <span
                aria-hidden="true"
                className={`${AVATAR} ${
                  author === "agent"
                    ? "bg-accent-soft text-accent-ink"
                    : "bg-brand-deep text-presence-ink"
                }`}
              >
                {author === "agent" ? "座" : "回"}
              </span>
            ) : null}
            <div
              className={`flex min-w-0 flex-1 flex-col gap-1 ${isCustomer ? "items-end" : "items-start"}`}
            >
              <span className="sr-only">{authorLabel(author)}</span>
              <div className={`${BUBBLE_BASE} ${tone}`}>{message.content}</div>
              {message.payload?.orders?.length ? (
                <ul className="m-0 flex w-full max-w-[560px] list-none flex-col gap-2 p-0">
                  {message.payload.orders.map((order) => (
                    <li key={order.order_id} className="w-full">
                      <OrderCard
                        order={order}
                        cancellation={cancellation}
                        onCancel={onCancelOrder}
                      />
                    </li>
                  ))}
                </ul>
              ) : null}
              <time
                className="px-0.5 text-[11px] tabular-nums text-text-3"
                dateTime={message.created_at}
              >
                {formatTime(message.created_at)}
              </time>
            </div>
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
            className="mt-1 h-2 w-2 shrink-0 animate-pulse motion-reduce:animate-none rounded-full bg-warning shadow-[0_0_0_4px_var(--halo-warning)]"
          />
          <div>
            <div className="text-sm font-semibold text-warning-ink">正在为你接通人工客服</div>
            <div className="mt-1 text-xs leading-relaxed text-warning-ink">
              接通后会在这里提示你，也可以先补充问题。
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
