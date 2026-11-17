"use client";

import type { Conversation, Customer } from "@/lib/session";

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
          <div className="conversation-card">
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
                  <span className="pill">{conversation.status}</span>
                </dd>
              </div>
            </dl>
            <p className="placeholder">消息功能下一刀接入</p>
          </div>
        ) : null}
      </section>
    </main>
  );
}
