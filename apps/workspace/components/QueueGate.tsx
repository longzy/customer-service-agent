"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getQueue, claimHandoff, type QueueItem } from "@/lib/queue";
import { ApiError, getSession, logout, type Session } from "@/lib/session";

const ROLE_LABEL: Record<string, string> = {
  agent: "坐席",
};

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
};

type RetryMode = "load" | "logout";

export function QueueGate() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [claimNotice, setClaimNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryMode, setRetryMode] = useState<RetryMode>("load");

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
      // 队列顺序由服务端 FIFO 契约决定；这里只渲染，不排序、不补齐字段。
      const queue = await getQueue();
      if (!queue) {
        router.replace("/login");
        return;
      }
      setItems(queue);
    } catch {
      setRetryMode("load");
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
      setRetryMode("logout");
      setError("退出失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  async function handleClaim(item: QueueItem) {
    setClaimingId(item.handoff_id);
    setClaimNotice(null);
    try {
      const result = await claimHandoff(item.handoff_id);
      if (!result) {
        router.replace("/login");
        return;
      }
      router.push(`/conversations/${result.conversation_id}`);
    } catch (claimError) {
      if (claimError instanceof ApiError && claimError.status === 404) {
        setClaimNotice("该交接单不存在或已被领取，队列已刷新");
        await load();
      } else if (claimError instanceof ApiError && claimError.status === 409) {
        setClaimNotice(
          claimError.code === "CONVERSATION_CLOSED"
            ? "该会话已结束"
            : "该会话已被其他坐席领取，队列已刷新",
        );
        await load();
      } else {
        setClaimNotice("领取失败，请重试");
      }
    } finally {
      setClaimingId(null);
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
  const retry = retryMode === "logout" ? () => void handleLogout() : () => void load();
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
            <button type="button" className="ghost" onClick={retry} disabled={busy || loading}>
              {retryMode === "logout" ? "重试退出" : "重试"}
            </button>
          </div>
        ) : null}
        <div className="conversation-card">
          <h2 className="notice">待接入队列</h2>
          {claimNotice ? (
            <p className="queue-notice" role="status">
              {claimNotice}
            </p>
          ) : null}
          {items === null ? (
            error ? null : (
              <div className="placeholder">加载中…</div>
            )
          ) : items.length === 0 ? (
            <div className="placeholder">暂无待接入会话</div>
          ) : (
            <ul className="queue-list">
              {items.map((item) => (
                <li className="queue-item" key={item.handoff_id}>
                  <div className="queue-item-head">
                    <span className="queue-customer">
                      {item.customer_display_name}（{item.customer_username}）
                    </span>
                    <span className="pill">{REASON_LABEL[item.reason] ?? item.reason}</span>
                    <span className="queue-wait">已等待 {item.waiting_seconds} 秒</span>
                  </div>
                  <p className="queue-last">{item.last_message || "（无客户消息）"}</p>
                  <div className="queue-footer">
                    <p className="queue-order">订单数 {item.order_count}</p>
                    <button
                      type="button"
                      className="enter queue-claim"
                      onClick={() => void handleClaim(item)}
                      disabled={claimingId !== null || loading || busy}
                    >
                      {claimingId === item.handoff_id ? "领取中…" : "领取"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
