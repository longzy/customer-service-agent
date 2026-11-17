"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getSession, logout, type Session } from "@/lib/session";

const ROLE_LABEL: Record<string, string> = {
  agent: "坐席",
};

export function QueueGate() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const current = await getSession();
      if (!current) {
        router.replace("/login");
        return;
      }
      setSession(current);
    } catch {
      setError("请求未完成，请重试");
    } finally {
      setLoading(false);
    }
  }, [router]);

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
        <span className="pill">{ROLE_LABEL[employee.role] ?? employee.role}</span>
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
            <button
              type="button"
              className="ghost"
              onClick={() => void handleLogout()}
              disabled={busy}
            >
              重试退出
            </button>
          </div>
        ) : null}
        <div className="conversation-card">
          <h2 className="notice">待接入队列</h2>
          <div className="placeholder">正在等待客户转人工</div>
        </div>
      </section>
    </main>
  );
}
