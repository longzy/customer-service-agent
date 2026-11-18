"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { ApiError } from "@/lib/api-client";
import {
  getConversation,
  getSession,
  logout,
  type Conversation,
  type Session,
} from "@/lib/session";

import { ChatShell } from "./ChatShell";

type RetryAction = "load" | "logout";

type GateError = {
  message: string;
  retry: RetryAction;
};

export function SessionGate() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedConversationId = searchParams.get("conversation_id");

  const [session, setSession] = useState<Session | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [conversationNotFound, setConversationNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<GateError | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConversationNotFound(false);
    try {
      const current = await getSession();
      if (!current) {
        router.replace("/login");
        return;
      }
      setSession(current);
      if (requestedConversationId) {
        // URL 指定会话时交给服务端校验归属；前端只展示 404 结果。
        try {
          setConversation(await getConversation(requestedConversationId));
        } catch (cause) {
          if (cause instanceof ApiError && cause.status === 404) {
            setConversation(null);
            setConversationNotFound(true);
          } else {
            throw cause;
          }
        }
      } else {
        setConversation(current.conversation);
      }
    } catch {
      setError({ message: "请求未完成，请重试", retry: "load" });
    } finally {
      setLoading(false);
    }
  }, [requestedConversationId, router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleLogout() {
    setBusy(true);
    setError(null);
    try {
      await logout();
      router.replace("/login");
    } catch {
      setError({ message: "退出失败，请重试", retry: "logout" });
    } finally {
      setBusy(false);
    }
  }

  function handleRetry() {
    if (error?.retry === "logout") {
      void handleLogout();
      return;
    }
    void load();
  }

  function handleBack() {
    setConversationNotFound(false);
    setConversation(session?.conversation ?? null);
    router.replace("/chat");
  }

  if (!session) {
    if (error) {
      return (
        <main className="app">
          <section className="content">
            <div className="error-box">
              <p role="alert">{error.message}</p>
              <button type="button" className="ghost" onClick={handleRetry} disabled={loading}>
                重试
              </button>
            </div>
          </section>
        </main>
      );
    }
    return (
      <main className="app" aria-busy={loading}>
        <p className="loading">加载中…</p>
      </main>
    );
  }

  return (
    <ChatShell
      key={conversation?.id ?? "none"}
      customer={session.customer}
      conversation={conversation}
      conversationNotFound={conversationNotFound}
      error={error?.message ?? null}
      busy={busy}
      onLogout={handleLogout}
      onRetry={error ? handleRetry : undefined}
      onBack={handleBack}
    />
  );
}
