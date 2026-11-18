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
    <div
      className={styles.list}
      ref={listRef}
      role="log"
      aria-live="polite"
      aria-label="消息记录"
    >
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
            {["查订单", "改地址", "转人工"].map((label) => (
              <button
                key={label}
                type="button"
                className={styles.quickButton}
                onClick={() => onQuick(label)}
              >
                {label}
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
