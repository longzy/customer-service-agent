"use client";

import { useEffect, useRef } from "react";

import { formatTime } from "@/lib/format";

import { AUTHOR_LABEL } from "../labels";
import type { Message } from "../types";

const BUBBLE =
  "max-w-[560px] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words";

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
      className="flex max-h-[380px] min-h-[140px] flex-col gap-3 overflow-y-auto rounded-xl border border-line-soft bg-surface-2 px-4 py-4"
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
            <p
              key={message.id}
              className="m-0 self-center rounded-full bg-surface px-3 py-1 text-center text-xs text-text-3"
            >
              {message.content}
            </p>
          );
        }
        const isCustomer = author === "customer";
        const tone = isCustomer
          ? "bg-accent text-white"
          : "border border-border bg-surface text-text";
        return (
          <article
            key={message.id}
            className={`flex max-w-[640px] flex-col gap-1 ${isCustomer ? "self-end items-end" : "items-start"}`}
            data-author={author}
          >
            <span className="text-[11px] text-text-3">
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
