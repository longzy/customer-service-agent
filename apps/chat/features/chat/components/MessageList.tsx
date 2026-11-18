"use client";

import { useEffect, useRef } from "react";

import type { Message, MessageAuthor } from "../types";

import styles from "./MessageList.module.css";

const AUTHOR_LABELS: Record<MessageAuthor, string> = {
  customer: "客户",
  ai: "客服 AI",
  agent: "坐席",
  system: "系统",
};

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

function authorLabel(authorType: MessageAuthor): string {
  return AUTHOR_LABELS[authorType] ?? "系统";
}

export function MessageList({ messages, loading, status, onQuick }: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = listRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages.length, loading, status]);

  return (
    <div className={styles.list} ref={listRef} role="log" aria-live="polite" aria-label="消息记录">
      {loading ? (
        <div className={styles.skeleton} aria-label="加载中">
          <span />
          <span />
          <span />
        </div>
      ) : null}

      {!loading && messages.length === 0 ? (
        <div className={styles.welcome}>
          <h2 className={styles.welcomeTitle}>你好，我是小回。</h2>
          <p className={styles.welcomeText}>
            我可以帮你查订单、改配送、办理退换。需要真人时，直接说「转人工」。
          </p>
          <div className={styles.quick}>
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.label}
                type="button"
                className={styles.quickButton}
                onClick={() => onQuick(action.label)}
              >
                {action.icon}
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
        const tone = isCustomer
          ? styles.bubbleCustomer
          : author === "agent"
            ? styles.bubbleAgent
            : styles.bubbleAi;

        if (isSystem) {
          return (
            <p key={message.id} className={styles.system}>
              {message.content}
            </p>
          );
        }

        return (
          <article
            key={message.id}
            className={`${styles.row} ${isCustomer ? styles.rowCustomer : ""}`}
            data-author={author}
          >
            {!isCustomer ? (
              <span className={styles.avatar} aria-hidden="true">
                {author === "agent" ? "座" : "回"}
              </span>
            ) : null}
            <div className={styles.stack}>
              <span className={styles.srOnly}>{authorLabel(author)}</span>
              <div className={`${styles.bubble} ${tone}`}>{message.content}</div>
            </div>
            <time className={styles.time} dateTime={message.created_at}>
              {formatTime(message.created_at)}
            </time>
          </article>
        );
      })}

      {status === "QUEUED" ? (
        <div className={styles.handoff} role="status">
          <span className={styles.pulse} aria-hidden="true" />
          <div>
            <div className={styles.handoffTitle}>正在为你接通人工客服</div>
            <div className={styles.handoffMeta}>接通后会在这里提示你，也可以先补充问题。</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
