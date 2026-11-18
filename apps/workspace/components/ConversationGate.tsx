"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { getConversation, type ConversationDetail } from "@/lib/conversation";
import { ApiError, getSession, logout, type Session } from "@/lib/session";

const STATUS_LABEL: Record<string, string> = {
  AI_ACTIVE: "AI 接待中",
  QUEUED: "排队中",
  CLAIMED: "已领取，等待接管",
  HUMAN_ACTIVE: "人工接入中",
  CLOSED: "已结束",
};

export function ConversationGate({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setMissing(false);
    try {
      const current = await getSession();
      if (!current) {
        router.replace("/login");
        return;
      }
      setSession(current);
      const detail = await getConversation(conversationId);
      if (!detail) {
        router.replace("/login");
        return;
      }
      setConversation(detail);
    } catch (loadError) {
      if (loadError instanceof ApiError && loadError.status === 404) {
        // 未领取、他人已领取或跨租户：统一不暴露会话是否存在。
        setMissing(true);
      } else {
        setError("请求未完成，请重试");
      }
    } finally {
      setLoading(false);
    }
  }, [conversationId, router]);

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
      setError("退出失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  if (!session) {
    if (error) {
      return (
        <main className="app">
          <section className="content">
            <div className="error-box">
              <p role="alert">{error}</p>
              <button
                type="button"
                className="ghost"
                onClick={() => void load()}
                disabled={loading}
              >
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

  const { employee } = session;
  return (
    <main className="app">
      <header className="topbar">
        <h1>客服工作台</h1>
        <Link className="ghost" href="/queue">
          返回队列
        </Link>
        <span className="who">
          {employee.display_name}（{employee.username}）
        </span>
        <button type="button" className="ghost" onClick={() => void handleLogout()} disabled={busy}>
          退出
        </button>
      </header>
      <section className="content">
        {error ? (
          <div className="error-box">
            <p role="alert">{error}</p>
            <button type="button" className="ghost" onClick={() => void load()} disabled={loading}>
              重试
            </button>
          </div>
        ) : null}
        <div className="conversation-card">
          <h2 className="notice">会话</h2>
          {missing ? (
            <div className="placeholder">未找到该会话，它可能尚未被领取或已由其他坐席接管。</div>
          ) : conversation === null ? (
            <div className="placeholder">加载中…</div>
          ) : (
            <dl className="meta">
              <div className="meta-item">
                <dt>会话编号</dt>
                <dd>
                  <code>{conversation.id}</code>
                </dd>
              </div>
              <div className="meta-item">
                <dt>状态</dt>
                <dd>
                  <span className="pill">
                    {STATUS_LABEL[conversation.status] ?? conversation.status}
                  </span>
                </dd>
              </div>
            </dl>
          )}
        </div>
      </section>
    </main>
  );
}
