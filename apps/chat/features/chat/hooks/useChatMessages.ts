"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api-client";
import type { Conversation } from "@/lib/session";

import { getMessages, newIdempotencyKey, sendMessage } from "../api/messages";
import type { Message, MessagePage } from "../types";

const MAX_MESSAGE_LENGTH = 500;
const POLL_INTERVAL_MS = 3000;

/**
 * 会话消息的读取与发送：初次全量、之后按游标增量轮询；发送失败复用幂等键。
 * 401 只由后端判定，收到后由本 hook 统一回登录页。
 */
export function useChatMessages(conversation: Conversation | null) {
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

  async function submitMessage(contentOverride?: string) {
    const content = (contentOverride ?? draft).trim();
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
      if (!contentOverride) {
        setDraft("");
      }
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

  const trimmedLength = draft.trim().length;
  const overLimit = trimmedLength > MAX_MESSAGE_LENGTH;
  const canSend = Boolean(conversationId) && !sending && trimmedLength > 0 && !overLimit;

  return {
    messages,
    status,
    loading,
    sending,
    messageError,
    draft,
    setDraft,
    trimmedLength,
    maxLength: MAX_MESSAGE_LENGTH,
    overLimit,
    canSend,
    submitMessage,
  };
}
