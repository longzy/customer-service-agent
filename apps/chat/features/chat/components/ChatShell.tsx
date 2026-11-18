"use client";

import type { FormEvent, KeyboardEvent } from "react";

import type { Conversation, Customer } from "@/lib/session";

import { useChatMessages } from "../hooks/useChatMessages";
import type { MessageAuthor } from "../types";

const QUEUE_NOTICE = "排队中，请稍候";

const AUTHOR_LABELS: Record<MessageAuthor, string> = {
  customer: "客户",
  ai: "客服 AI",
  agent: "坐席",
  system: "系统",
};

type ChatShellProps = {
  customer: Customer;
  conversation: Conversation | null;
  conversationNotFound?: boolean;
  error?: string | null;
  busy?: boolean;
  onLogout: () => void;
  onRetry?: () => void;
  onBack?: () => void;
};

function authorLabel(authorType: MessageAuthor): string {
  return AUTHOR_LABELS[authorType] ?? "系统";
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export function ChatShell({
  customer,
  conversation,
  conversationNotFound = false,
  error = null,
  busy = false,
  onLogout,
  onRetry,
  onBack,
}: ChatShellProps) {
  const {
    messages,
    status,
    loading,
    sending,
    messageError,
    draft,
    setDraft,
    trimmedLength,
    maxLength,
    overLimit,
    canSend,
    submitMessage,
  } = useChatMessages(conversation);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitMessage();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter 发送，Shift+Enter 换行；输入法合成中的 Enter 不发送。
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submitMessage();
    }
  }

  const visibleMessages =
    status === "QUEUED"
      ? messages.filter(
          (message) =>
            !(message.author_type === "system" && message.content.trim() === QUEUE_NOTICE),
        )
      : messages;

  return (
    <main className="app">
      <header className="topbar">
        <h1>客服中心</h1>
        <span className="who">{customer.display_name}</span>
        <button type="button" className="ghost" onClick={onLogout} disabled={busy}>
          退出
        </button>
      </header>
      <section className="content">
        {error ? (
          <div className="error-box">
            <p role="alert">{error}</p>
            {onRetry ? (
              <button type="button" className="ghost" onClick={onRetry} disabled={busy}>
                重试
              </button>
            ) : null}
          </div>
        ) : null}
        {conversationNotFound ? (
          <div className="conversation-card">
            <p className="notice" role="alert">
              会话不存在
            </p>
            <p className="login-note">该会话不存在，或当前账号无权访问。</p>
            {onBack ? (
              <button type="button" className="ghost" onClick={onBack}>
                返回
              </button>
            ) : null}
          </div>
        ) : conversation ? (
          <div className="conversation-card chat-card">
            <div className="chat-head">
              <dl className="meta">
                <div className="meta-item">
                  <dt>会话 ID</dt>
                  <dd>
                    <code>{conversation.id}</code>
                  </dd>
                </div>
                <div className="meta-item">
                  <dt>状态</dt>
                  <dd>
                    <span className="pill">{status}</span>
                  </dd>
                </div>
              </dl>
              {status === "QUEUED" ? (
                <p className="queue-notice" role="status">
                  {QUEUE_NOTICE}
                </p>
              ) : null}
            </div>
            {messageError ? (
              <div className="error-box">
                <p role="alert">{messageError}</p>
              </div>
            ) : null}
            <div className="message-list" role="log" aria-live="polite" aria-label="消息记录">
              {loading ? <p className="message-loading">加载中…</p> : null}
              {!loading && visibleMessages.length === 0 ? (
                <p className="placeholder">还没有消息，发送第一条吧</p>
              ) : null}
              {visibleMessages.map((message) => (
                <article
                  key={message.id}
                  className={`message message-${message.author_type}`}
                  data-author={message.author_type}
                >
                  <div className="message-head">
                    <span className="message-author">{authorLabel(message.author_type)}</span>
                    <time dateTime={message.created_at}>{formatTime(message.created_at)}</time>
                  </div>
                  <p className="message-content">{message.content}</p>
                </article>
              ))}
            </div>
            <form className="composer" onSubmit={handleSubmit}>
              <label className="sr-only" htmlFor="message-input">
                消息
              </label>
              <textarea
                id="message-input"
                name="content"
                rows={2}
                placeholder="输入消息…"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleKeyDown}
                aria-invalid={overLimit}
                aria-describedby="message-hint"
              />
              <div className="composer-actions">
                <span
                  id="message-hint"
                  className={overLimit ? "composer-hint over-limit" : "composer-hint"}
                >
                  {trimmedLength}/{maxLength}
                </span>
                <button type="submit" className="send" disabled={!canSend}>
                  {sending ? "发送中…" : "发送"}
                </button>
              </div>
            </form>
          </div>
        ) : null}
      </section>
    </main>
  );
}
