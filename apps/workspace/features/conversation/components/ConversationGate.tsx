"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api-client";
import { getSession, logout, type Session } from "@/lib/session";

import { getConversation, takeOverConversation } from "../api/conversation";
import { useConversationActions } from "../hooks/useConversationActions";
import { mergeConversationStatus } from "../status";
import type { ConversationDetail, MessagePage } from "../types";

import { ConversationDetailPanel } from "./ConversationDetailPanel";
import { ConversationThread } from "./ConversationThread";
import { WorkspaceNav } from "@/features/queue/components/WorkspaceNav";

const ROLE_LABEL: Record<string, string> = { agent: "坐席" };

export function ConversationGate({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const applyStatus = useCallback((status: MessagePage["status"], message?: string) => {
    setConversation((current) => mergeConversationStatus(current, status));
    if (message !== undefined) {
      setNotice(message);
    }
  }, []);
  const handleChanged = useCallback(
    (status: MessagePage["status"], message: string) => {
      applyStatus(status, message);
      setError(null);
    },
    [applyStatus],
  );
  const {
    busy: acting,
    error: actionError,
    clearError,
    close,
    returnToAi,
  } = useConversationActions(conversationId, handleChanged);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    setMissing(false);
    clearError();
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
  }, [clearError, conversationId, router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleTakeOver() {
    setBusy(true);
    setError(null);
    setNotice(null);
    clearError();
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
        <main className="grid min-h-dvh place-items-center bg-bg p-6">
          <div className="w-full max-w-[380px] rounded-2xl border border-border bg-surface p-6 text-center shadow-panel">
            <p className="m-0 text-sm text-danger" role="alert">
              {error}
            </p>
            <Button className="mt-4" onClick={() => void load()} disabled={loading}>
              重试
            </Button>
          </div>
        </main>
      );
    }
    return (
      <main className="grid min-h-dvh place-items-center bg-bg" aria-busy={loading}>
        <p className="flex items-center gap-2 text-sm text-text-3">
          <span
            aria-hidden="true"
            className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-border border-t-accent motion-reduce:animate-none"
          />
          加载中…
        </p>
      </main>
    );
  }

  const { employee } = session;
  const roleLabel = ROLE_LABEL[employee.role] ?? employee.role;

  return (
    <main className="flex h-dvh overflow-hidden bg-bg">
      <WorkspaceNav
        agentName={employee.display_name}
        roleLabel={roleLabel}
        busy={busy}
        onLogout={() => void handleLogout()}
      />

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-surface px-8 max-[1023px]:px-4">
          <Link
            className="rounded-md text-sm text-text-2 transition-colors hover:text-text focus-visible:outline-none focus-visible:shadow-focus"
            href="/queue"
          >
            ← 待接入队列
          </Link>
          <span aria-hidden="true" className="text-border-strong">
            /
          </span>
          <b className="text-sm font-medium text-text">会话详情</b>
          <span className="ml-auto text-xs text-text-3">
            {employee.display_name}（{employee.username}）
          </span>
          <Button variant="secondary" size="sm" onClick={() => void handleLogout()} disabled={busy}>
            退出
          </Button>
        </header>

        <div className="relative min-h-0 flex-1 overflow-y-auto px-8 py-6 max-[1023px]:px-4 max-[1023px]:py-4">
          <div className="mx-auto w-full max-w-[1160px]">
            {error && conversation === null ? (
              <div className="rounded-2xl border border-border bg-surface p-6 shadow-panel">
                <p className="m-0 text-sm text-danger" role="alert">
                  {error}
                </p>
                <Button className="mt-4" onClick={() => void load()} disabled={loading}>
                  重试
                </Button>
              </div>
            ) : null}

            {missing ? (
              <div className="grid place-items-center rounded-2xl border border-border bg-surface p-12 text-center shadow-panel">
                <div className="max-w-[420px]">
                  <h2 className="m-0 text-base font-semibold">未找到该会话</h2>
                  <p className="mt-2 text-sm leading-relaxed text-text-2">
                    它可能尚未被领取，或已由其他坐席接管。
                  </p>
                  <Link
                    className="mt-5 inline-flex h-9 items-center rounded-lg border border-border bg-surface px-4 text-sm text-text transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:shadow-focus"
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
              <div className="flex flex-col gap-5">
                <ConversationDetailPanel
                  detail={conversation}
                  feedback={{ notice, error: actionError ?? error }}
                  actions={{
                    busy,
                    acting,
                    onTakeOver: () => void handleTakeOver(),
                    onClose: close,
                    onReturnToAi: returnToAi,
                  }}
                />
                <ConversationThread
                  conversationId={conversation.id}
                  status={conversation.status}
                  live={conversation.status === "CLAIMED" || conversation.status === "HUMAN_ACTIVE"}
                  onStatus={applyStatus}
                />
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
