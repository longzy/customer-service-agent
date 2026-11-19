"use client";

import { DeniedState, PageLoading, QueueError } from "./QueueStates";

type QueueFallbackProps = {
  denied: boolean;
  error: string | null;
  errorCode?: string;
  loading: boolean;
  onRetry: () => void;
  onLogout: () => void;
};

export function QueueFallback({
  denied,
  error,
  errorCode,
  loading,
  onRetry,
  onLogout,
}: QueueFallbackProps) {
  if (denied) {
    return <DeniedState onLogout={onLogout} />;
  }
  if (error) {
    return <QueueError message={error} code={errorCode} onRetry={onRetry} retrying={loading} />;
  }
  return <PageLoading label={loading ? "加载中…" : "无法确认登录状态"} />;
}
