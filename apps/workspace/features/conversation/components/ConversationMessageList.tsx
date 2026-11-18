"use client";

import { useEffect, useRef } from "react";

import { formatTime } from "@/lib/format";

import type { Message } from "../types";

const AUTHOR_LABEL: Record<string, string> = {
  customer: "客户",
  ai: "客服 AI",
  agent: "坐席",
  system: "系统",
};

const BUBBLE = "rounded-xl px-3.5 py-2.5 text-sm leading-[1.7] whitespace-pre-wrap break-words";

type ConversationMessageListProps = {
  messages: Message[];
  loading: boolean;
};

/** 实时消息流：只展示接口返回的消息，不把交接单快照混进来。 */
export function ConversationMessageList({ messages, loading }: ConversationMessageListProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = listRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages.length, loading]);

  return (
    <div
      className="flex max-h-[360px] min-h-[120px] flex-col gap-2.5 overflow-y-auto rounded-[9px] border border-line-soft bg-surface-soft px-3 py-3"
      ref={listRef}
      role="log"
      aria-live="polite"
      aria-label="实时消息"
    >
      {loading ? (
        <p className="m-0 text-sm text-text-3" aria-busy="true">
          加载消息…
        </p>
      ) : null}

      {!loading && messages.length === 0 ? (
        <p className="m-0 text-sm text-text-3">暂无实时消息。</p>
      ) : null}

      {messages.map((message) => {
        const author = message.author_type;
        if (author === "system") {
          return (
            <p key={message.id} className="m-0 self-center text-center text-xs text-text-3">
              {message.content}
            </p>
          );
        }
        const isCustomer = author === "customer";
        const tone = isCustomer
          ? "bg-brand-deep text-paper rounded-tr-[4px]"
          : author === "agent"
            ? "border border-accent-line bg-accent-soft text-accent-ink rounded-tl-[4px]"
            : "border border-border bg-surface rounded-tl-[4px]";
        return (
          <article
            key={message.id}
            className={`flex max-w-[640px] flex-col gap-1 ${isCustomer ? "self-end items-end" : "items-start"}`}
            data-author={author}
          >
            <span className="text-xs text-text-3">
              {AUTHOR_LABEL[author] ?? "系统"} ·{" "}
              <time dateTime={message.created_at}>{formatTime(message.created_at)}</time>
            </span>
            <div className={`${BUBBLE} ${tone}`}>{message.content}</div>
          </article>
        );
      })}
    </div>
  );
}
