"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api-client";

import {
  confirmCancellation,
  createCancellation,
  declineCancellation,
  refreshCancellation,
} from "../api/cancellations";
import type { CancellationTask, CustomerOrderSummary } from "../types";

/**
 * 取消弹层的判别状态；互斥状态不拆成多个布尔量（FE-CMP-05）。
 * `confirm` 表示任务已生成但尚未提交，是 AC-60 的“尚未提交”卡片。
 */
export type CancelDialogState =
  | { kind: "closed" }
  | { kind: "loading"; order: CustomerOrderSummary }
  | { kind: "confirm"; order: CustomerOrderSummary; task: CancellationTask }
  | { kind: "submitting"; order: CustomerOrderSummary; task: CancellationTask }
  | { kind: "result"; order: CustomerOrderSummary; task: CancellationTask }
  | { kind: "error"; order: CustomerOrderSummary | null; message: string };

const NOT_FOUND_TEXT = "没有查到你名下的这笔订单";
const NOT_CANCELABLE_TEXT = "该订单当前不能取消";
const UNAVAILABLE_TEXT = "服务暂时不可用，请稍后重试";
const FALLBACK_TEXT = "操作失败，请稍后重试";

function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) {
      return NOT_FOUND_TEXT;
    }
    if (error.status === 409) {
      return NOT_CANCELABLE_TEXT;
    }
    if (error.status === 503 || error.status === 504) {
      return UNAVAILABLE_TEXT;
    }
  }
  return FALLBACK_TEXT;
}

/**
 * 取消流程的交互状态：点“取消订单”先创建/复用任务再显示确认卡片；
 * 确认后只提交一次，结果卡可刷新到最终状态。列表刷新通过 `onChanged` 通知页面。
 */
export function useCancellation(onChanged: () => void) {
  const router = useRouter();
  const [state, setState] = useState<CancelDialogState>({ kind: "closed" });

  const handleAuth = useCallback(
    (error: unknown): boolean => {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return true;
      }
      return false;
    },
    [router],
  );

  const open = useCallback(
    async (order: CustomerOrderSummary) => {
      setState({ kind: "loading", order });
      try {
        const task = await createCancellation(order.order_id);
        setState(
          task.can_confirm ? { kind: "confirm", order, task } : { kind: "result", order, task },
        );
      } catch (error) {
        if (handleAuth(error)) {
          return;
        }
        setState({ kind: "error", order, message: messageOf(error) });
      }
    },
    [handleAuth],
  );

  const confirm = useCallback(async () => {
    if (state.kind !== "confirm") {
      return;
    }
    const { order, task } = state;
    setState({ kind: "submitting", order, task });
    try {
      const result = await confirmCancellation(task.id);
      setState({ kind: "result", order, task: result });
      onChanged();
    } catch (error) {
      if (handleAuth(error)) {
        return;
      }
      setState({ kind: "error", order, message: messageOf(error) });
    }
  }, [handleAuth, onChanged, state]);

  const decline = useCallback(async () => {
    if (state.kind !== "confirm") {
      return;
    }
    const { order, task } = state;
    setState({ kind: "submitting", order, task });
    try {
      await declineCancellation(task.id);
      setState({ kind: "closed" });
      onChanged();
    } catch (error) {
      if (handleAuth(error)) {
        return;
      }
      setState({ kind: "error", order, message: messageOf(error) });
    }
  }, [handleAuth, onChanged, state]);

  const refresh = useCallback(async () => {
    if (state.kind !== "result") {
      return;
    }
    const { order, task } = state;
    try {
      const latest = await refreshCancellation(task.id);
      setState({ kind: "result", order, task: latest });
      onChanged();
    } catch (error) {
      if (handleAuth(error)) {
        return;
      }
      setState({ kind: "error", order, message: messageOf(error) });
    }
  }, [handleAuth, onChanged, state]);

  const close = useCallback(() => setState({ kind: "closed" }), []);

  /**
   * 列表项的“刷新结果”：任务已提交但未收敛时按 id 拉一次最新状态。
   * 成功后通知页面重读列表；失败沿用弹层的错误文案，不静默丢弃。
   */
  const refreshTask = useCallback(
    async (taskId: string) => {
      try {
        const latest = await refreshCancellation(taskId);
        onChanged();
        return latest;
      } catch (error) {
        if (handleAuth(error)) {
          return null;
        }
        setState({ kind: "error", order: null, message: messageOf(error) });
        return null;
      }
    },
    [handleAuth, onChanged],
  );

  return { state, open, confirm, decline, refresh, refreshTask, close };
}
