"use client";

import type { Conversation, Customer } from "@/lib/session";

import { useChatMessages } from "../hooks/useChatMessages";
import { ChatBrand } from "./ChatBrand";
import { ChatComposer } from "./ChatComposer";
import { MessageList } from "./MessageList";
import styles from "./ChatShell.module.css";

const QUEUE_NOTICE = "排队中，请稍候";

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

function statusMeta(status: string): { label: string; tone: string } {
  switch (status) {
    case "QUEUED":
    case "CLAIMED":
      return { label: "人工接入中", tone: styles.chipWarn };
    case "HUMAN_ACTIVE":
      return { label: "人工服务中", tone: styles.chipLive };
    case "CLOSED":
      return { label: "已结束", tone: styles.chipNeutral };
    case "AI_ACTIVE":
      return { label: "AI 服务中", tone: styles.chipLive };
    default:
      return { label: status, tone: styles.chipNeutral };
  }
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

  const meta = statusMeta(status);
  const visibleMessages =
    status === "QUEUED"
      ? messages.filter(
          (message) =>
            !(message.author_type === "system" && message.content.trim() === QUEUE_NOTICE),
        )
      : messages;

  return (
    <main className={styles.page}>
      <ChatBrand customerName={customer.display_name} busy={busy} onLogout={onLogout} />

      <section className={styles.chat}>
        <header className={styles.head}>
          <div>
            <p className={styles.kicker}>ONLINE SUPPORT</p>
            <h1 className={styles.title}>在线支持</h1>
          </div>
          <span className={`${styles.chip} ${meta.tone}`}>
            <span className={styles.chipDot} aria-hidden="true" />
            {meta.label}
          </span>
        </header>

        {error ? (
          <div className={styles.error} role="alert">
            <p>{error}</p>
            {onRetry ? (
              <button className={styles.retry} type="button" onClick={onRetry} disabled={busy}>
                重试
              </button>
            ) : null}
          </div>
        ) : null}

        {conversationNotFound ? (
          <div className={styles.notFound}>
            <div className={styles.notFoundCard}>
              <h2>会话不存在</h2>
              <p>该会话不存在，或当前账号无权访问。</p>
              {onBack ? (
                <button className={styles.retry} type="button" onClick={onBack}>
                  返回
                </button>
              ) : null}
            </div>
          </div>
        ) : conversation ? (
          <>
            {messageError ? (
              <p className={styles.notice} role="alert">
                {messageError}
              </p>
            ) : null}
            <MessageList
              messages={visibleMessages}
              loading={loading}
              status={status}
              onQuick={(text) => void submitMessage(text)}
            />
            <div className={styles.composerArea}>
              <ChatComposer
                draft={draft}
                setDraft={setDraft}
                sending={sending}
                overLimit={overLimit}
                trimmedLength={trimmedLength}
                maxLength={maxLength}
                canSend={canSend}
                onSubmit={() => void submitMessage()}
              />
            </div>
          </>
        ) : null}
      </section>
    </main>
  );
}
