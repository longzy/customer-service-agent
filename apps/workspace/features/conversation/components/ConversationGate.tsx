"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { getSession, logout, type Session } from "@/lib/session";

import { getConversation, takeOverConversation } from "../api/conversation";
import type { ConversationDetail } from "../types";

import { ConversationDetailPanel } from "./ConversationDetail";

const BUTTON =
  "h-8 rounded-md border border-border bg-surface px-3 text-sm text-text hover:border-border-strong focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-text-3";

export function ConversationGate({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
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
      } else if (loadError instanceof ApiError && loadError.status === 403) {
        router.replace("/login");
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

  async function handleTakeOver() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await takeOverConversation(conversationId);
      if (!result) {
        router.replace("/login");
        return;
      }
      setConversation((current) =>
        current === null ? current : { ...current, status: result.status },
      );
      setNotice("已接管会话，客户将看到“人工已接入”。");
    } catch (takeoverError) {
      if (takeoverError instanceof ApiError && takeoverError.status === 404) {
        setError("会话状态已变化，请刷新后重试。");
      } else if (
        takeoverError instanceof ApiError &&
        takeoverError.code === "CONVERSATION_CLOSED"
      ) {
        setError("会话已结束，无法接管。");
      } else {
        setError("接管失败，请重试。");
      }
    } finally {
      setBusy(false);
    }
  }

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
        <main className="grid min-h-screen place-items-center bg-bg p-6">
          <div className="w-full max-w-[360px] rounded-xl border border-border bg-surface p-5 text-center">
            <p className="m-0 text-sm text-danger" role="alert">
              {error}
            </p>
            <button
              type="button"
              className={`${BUTTON} mt-4`}
              onClick={() => void load()}
              disabled={loading}
            >
              重试
            </button>
          </div>
        </main>
      );
    }
    return (
      <main className="grid min-h-screen place-items-center bg-bg" aria-busy={loading}>
        <p className="text-sm text-text-3">加载中…</p>
      </main>
    );
  }

  const { employee } = session;
  return (
    <main className="flex min-h-screen flex-col bg-bg">
      <header className="flex h-[60px] shrink-0 items-center gap-2 border-b border-border bg-surface px-6 max-[1023px]:px-4">
        <Link
          className="text-sm text-text-3 hover:text-text focus-visible:outline-none focus-visible:shadow-focus"
          href="/queue"
        >
          ← 待接入队列
        </Link>
        <span aria-hidden="true" className="text-border-strong">
          /
        </span>
        <b className="text-sm font-medium text-text">会话详情</b>
        <span className="ml-auto text-sm text-text-2 max-[767px]:hidden">
          {employee.display_name}（{employee.username}）
        </span>
        <button
          type="button"
          className={BUTTON}
          onClick={() => void handleLogout()}
          disabled={busy}
        >
          退出
        </button>
      </header>

      <section className="flex min-w-0 flex-1 flex-col gap-4 px-6 py-5 max-[1023px]:px-4">
        {error && conversation === null ? (
          <div className="rounded-xl border border-border bg-surface p-5">
            <p className="m-0 text-sm text-danger" role="alert">
              {error}
            </p>
            <button
              type="button"
              className={`${BUTTON} mt-3`}
              onClick={() => void load()}
              disabled={loading}
            >
              重试
            </button>
          </div>
        ) : null}

        {missing ? (
          <div className="grid place-items-center rounded-xl border border-border bg-surface p-10 text-center">
            <div className="max-w-[420px]">
              <h2 className="m-0 text-base font-semibold">未找到该会话</h2>
              <p className="mt-2 text-sm leading-[1.7] text-text-2">
                它可能尚未被领取，或已由其他坐席接管。
              </p>
              <Link
                className="mt-4 inline-flex h-8 items-center rounded-md border border-border px-3 text-sm text-text hover:border-border-strong focus-visible:outline-none focus-visible:shadow-focus"
                href="/queue"
              >
                返回队列
              </Link>
            </div>
          </div>
        ) : conversation === null ? (
          <p className="text-sm text-text-3" aria-busy={loading}>
            {loading ? "加载中…" : "暂无会话数据。"}
          </p>
        ) : (
          <ConversationDetailPanel
            detail={conversation}
            busy={busy}
            notice={notice}
            error={error}
            onTakeOver={() => void handleTakeOver()}
          />
        )}
      </section>
    </main>
  );
}
