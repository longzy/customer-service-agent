"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";

import {
  getConversationMessages,
  newIdempotencyKey,
  sendConversationReply,
} from "../api/conversation";
import type { Message, MessagePage } from "../types";

const POLL_INTERVAL_MS = 3000;
const MAX_REPLY_LENGTH = 500;

/**
 * 工作台会话消息：首轮全量、之后按 `after_id` 每 3s 增量轮询（plan 3.3.3）。
 * 消息页回传的 `status` 通过 `onStatus` 交给页面，关闭/转回后无需再读详情。
 * 发送失败保留草稿与幂等键，重试不会产生两条回复（INV-07）。
 */
export function useConversationMessages(
  conversationId: string,
  onStatus?: (status: MessagePage["status"]) => void,
  live = true,
) {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const afterIdRef = useRef(0);
  const pendingKeyRef = useRef<string | null>(null);
  const failedContentRef = useRef<string | null>(null);
  const stoppedRef = useRef(false);
  const mountedRef = useRef(true);
  const onStatusRef = useRef(onStatus);

  useEffect(() => {
    onStatusRef.current = onStatus;
  }, [onStatus]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const mergePage = useCallback((page: MessagePage) => {
    onStatusRef.current?.(page.status);
    // updater 必须是纯函数；按 id 去重，轮询与发送响应重叠时不会重复显示。
    setMessages((previous) => {
      const known = new Set(previous.map((message) => message.id));
      const fresh = page.messages.filter((message) => !known.has(message.id));
      if (fresh.length === 0) {
        return previous;
      }
      return [...previous, ...fresh].sort((left, right) => left.id - right.id);
    });
  }, []);

  const applyPage = useCallback(
    (page: MessagePage) => {
      afterIdRef.current = Math.max(afterIdRef.current, page.after_id);
      mergePage(page);
    },
    [mergePage],
  );

  const handleFailure = useCallback(
    (cause: unknown, fallback: string) => {
      if (cause instanceof ApiError && cause.status === 401) {
        stoppedRef.current = true;
        router.replace("/login");
        return;
      }
      setError(cause instanceof ApiError ? cause.message : fallback);
    },
    [router],
  );

  useEffect(() => {
    let cancelled = false;
    stoppedRef.current = false;
    if (!live) {
      setLoading(false);
      return;
    }

    async function load(afterId: number) {
      try {
        const page = await getConversationMessages(conversationId, afterId);
        if (cancelled) {
          return;
        }
        if (page === null) {
          stoppedRef.current = true;
          router.replace("/login");
          return;
        }
        applyPage(page);
      } catch (cause) {
        if (!cancelled) {
          handleFailure(cause, "消息加载失败，请稍后重试");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

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
  }, [conversationId, applyPage, handleFailure, live, router]);

  const submitReply = useCallback(async () => {
    const content = draft.trim();
    if (!conversationId || sending || !content || content.length > MAX_REPLY_LENGTH) {
      return;
    }
    setSending(true);
    setError(null);
    const key =
      pendingKeyRef.current && failedContentRef.current === content
        ? pendingKeyRef.current
        : newIdempotencyKey();
    pendingKeyRef.current = key;
    failedContentRef.current = content;
    try {
      const page = await sendConversationReply(conversationId, content, key);
      if (!mountedRef.current) {
        return;
      }
      if (page === null) {
        stoppedRef.current = true;
        router.replace("/login");
        return;
      }
      pendingKeyRef.current = null;
      failedContentRef.current = null;
      // 发送响应只合并展示，不推进轮询游标：客户消息可能在回复前落库，
      // 推进到回复 id 会让下一次轮询跳过它。
      mergePage(page);
      setDraft("");
    } catch (cause) {
      if (!mountedRef.current) {
        return;
      }
      const closed = cause instanceof ApiError && cause.code === "CONVERSATION_CLOSED";
      setError(closed ? "会话已结束，无法回复。" : "回复发送失败，请重试。");
    } finally {
      if (mountedRef.current) {
        setSending(false);
      }
    }
  }, [mergePage, conversationId, draft, router, sending]);

  const trimmedLength = draft.trim().length;
  const overLimit = trimmedLength > MAX_REPLY_LENGTH;
  const canSend = !sending && trimmedLength > 0 && !overLimit;

  return {
    messages,
    loading,
    sending,
    error,
    draft,
    setDraft,
    trimmedLength,
    maxLength: MAX_REPLY_LENGTH,
    overLimit,
    canSend,
    submitReply,
  };
}
