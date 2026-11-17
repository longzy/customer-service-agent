"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useRouter } from "next/navigation";

import {
  ApiError,
  getMessages,
  newIdempotencyKey,
  sendMessage,
  type Conversation,
  type Customer,
  type Message,
  type MessageAuthor,
  type MessagePage,
} from "@/lib/session";

const MAX_MESSAGE_LENGTH = 500;
const POLL_INTERVAL_MS = 3000;
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
  const router = useRouter();
  const conversationId = conversation?.id ?? null;

  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState(conversation?.status ?? "");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(Boolean(conversationId));
  const [sending, setSending] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);

  const afterIdRef = useRef(conversation?.after_id ?? 0);
  // 失败后重发同一内容时复用幂等键，避免网络重试造成重复消息。
  const pendingKeyRef = useRef<string | null>(null);
  const failedContentRef = useRef<string | null>(null);
  const stoppedRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const applyPage = useCallback((page: MessagePage) => {
    setStatus(page.status);
    afterIdRef.current = Math.max(afterIdRef.current, page.after_id);
    // updater 必须是纯函数：dev StrictMode 会双调用它，不能在里面写 ref。
    // 以已有消息 id 去重，组件重挂载后重新拉取也能恢复。
    setMessages((previous) => {
      const known = new Set(previous.map((message) => message.id));
      const fresh = page.messages.filter((message) => !known.has(message.id));
      if (fresh.length === 0) {
        return previous;
      }
      return [...previous, ...fresh].sort((left, right) => left.id - right.id);
    });
  }, []);

  const handleFailure = useCallback(
    (cause: unknown, fallback: string) => {
      if (cause instanceof ApiError && cause.status === 401) {
        // 会话失效只由后端判定，前端收到 401 直接回登录页。
        stoppedRef.current = true;
        router.replace("/login");
        return;
      }
      const message = cause instanceof ApiError ? cause.message : fallback;
      setMessageError(message);
    },
    [router],
  );

  useEffect(() => {
    if (!conversationId) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    stoppedRef.current = false;
    setLoading(true);

    async function load(afterId: number) {
      try {
        const page = await getMessages(afterId);
        if (cancelled) {
          return;
        }
        applyPage(page);
      } catch (cause) {
        if (cancelled) {
          return;
        }
        handleFailure(cause, "消息加载失败，请稍后重试");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    // 初次拉取用 0 恢复全部历史，之后每 3s 用最新游标取增量。
    void load(0);
    const timer = setInterval(() => {
      if (!stoppedRef.current) {
        void load(afterIdRef.current);
      }
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [conversationId, applyPage, handleFailure]);

  async function submitMessage() {
    const content = draft.trim();
    if (!conversationId || sending || !content || content.length > MAX_MESSAGE_LENGTH) {
      return;
    }
    setSending(true);
    setMessageError(null);
    const key =
      pendingKeyRef.current && failedContentRef.current === content
        ? pendingKeyRef.current
        : newIdempotencyKey();
    pendingKeyRef.current = key;
    failedContentRef.current = content;
    try {
      const page = await sendMessage(content, key);
      if (!mountedRef.current) {
        return;
      }
      pendingKeyRef.current = null;
      failedContentRef.current = null;
      applyPage(page);
      setDraft("");
    } catch (cause) {
      if (!mountedRef.current) {
        return;
      }
      handleFailure(cause, "发送失败，请稍后重试");
    } finally {
      if (mountedRef.current) {
        setSending(false);
      }
    }
  }

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

  const trimmedLength = draft.trim().length;
  const overLimit = trimmedLength > MAX_MESSAGE_LENGTH;
  const canSend = Boolean(conversationId) && !sending && trimmedLength > 0 && !overLimit;
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
                  {trimmedLength}/{MAX_MESSAGE_LENGTH}
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
