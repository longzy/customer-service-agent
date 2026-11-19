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

import { ChatLoading } from "./ChatLoading";
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
        <main className="grid min-h-screen place-items-center bg-bg p-10 font-sans">
          <div className="w-full max-w-[420px] rounded-xl border border-border bg-surface p-6 text-center shadow-panel">
            <p className="m-0 text-sm leading-[1.7] text-text-2" role="alert">
              {error.message}
            </p>
            <button
              className="mt-4 h-9 rounded-md border border-border bg-surface px-3.5 text-sm text-text hover:border-border-strong focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50"
              type="button"
              onClick={handleRetry}
              disabled={loading}
            >
              重试
            </button>
          </div>
        </main>
      );
    }
    return <ChatLoading />;
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
