"use client";

import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";

import { closeConversation, newIdempotencyKey, returnConversationToAi } from "../api/conversation";
import type { MessagePage } from "../types";

export type ConversationActionKind = "close" | "return";

type Action = {
  kind: ConversationActionKind;
  request: (idempotencyKey: string) => Promise<MessagePage | null>;
  successNotice: string;
  fallbackError: string;
};

const CLOSED_ERROR = "会话已结束，无法操作。";
const STALE_ERROR = "会话状态已变化，请刷新后重试。";

/**
 * 坐席关闭/转回 AI：失败保留当前状态并提示；成功后由页面更新状态与提示。
 * 同一动作失败重试复用幂等键（INV-07），切换动作或成功后换新键。
 */
export function useConversationActions(
  conversationId: string,
  onChanged: (status: MessagePage["status"], notice: string) => void,
) {
  const router = useRouter();
  const [busy, setBusy] = useState<ConversationActionKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const retryRef = useRef<{ kind: ConversationActionKind; key: string } | null>(null);

  const run = useCallback(
    async (action: Action) => {
      setBusy(action.kind);
      setError(null);
      const key =
        retryRef.current?.kind === action.kind ? retryRef.current.key : newIdempotencyKey();
      retryRef.current = { kind: action.kind, key };
      try {
        const page = await action.request(key);
        if (page === null) {
          router.replace("/login");
          return;
        }
        retryRef.current = null;
        onChanged(page.status, action.successNotice);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 401) {
          router.replace("/login");
          return;
        }
        if (cause instanceof ApiError && cause.status === 409) {
          setError(CLOSED_ERROR);
        } else if (cause instanceof ApiError && cause.status === 404) {
          setError(STALE_ERROR);
        } else {
          setError(action.fallbackError);
        }
      } finally {
        setBusy(null);
      }
    },
    [onChanged, router],
  );

  const close = useCallback(() => {
    void run({
      kind: "close",
      request: (key) => closeConversation(conversationId, key),
      successNotice: "已关闭会话，客户将看到“会话已结束”。",
      fallbackError: "关闭失败，请重试。",
    });
  }, [conversationId, run]);

  const returnToAi = useCallback(() => {
    void run({
      kind: "return",
      request: (key) => returnConversationToAi(conversationId, key),
      successNotice: "已转回 AI，客户可继续和 AI 对话。",
      fallbackError: "转回失败，请重试。",
    });
  }, [conversationId, run]);

  const clearError = useCallback(() => setError(null), []);

  return { busy, error, clearError, close, returnToAi };
}
