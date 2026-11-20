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
    return (
      <main className="grid min-h-dvh place-items-center bg-bg p-6">
        <DeniedState onLogout={onLogout} />
      </main>
    );
  }
  if (error) {
    return (
      <main className="grid min-h-dvh place-items-center bg-bg p-6">
        <QueueError message={error} code={errorCode} onRetry={onRetry} retrying={loading} />
      </main>
    );
  }
  return <PageLoading label={loading ? "加载中…" : "无法确认登录状态"} />;
}
