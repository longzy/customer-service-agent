"use client";

import { Check, CircleAlert, LockKeyhole } from "lucide-react";

import { Button } from "@/components/ui/Button";

const STATE =
  "flex min-h-0 flex-1 flex-col items-center justify-center gap-2 rounded-2xl border border-border bg-surface p-8 text-center shadow-panel";
const ICON = "mb-1 grid h-11 w-11 place-items-center rounded-full";
const TITLE = "m-0 text-base font-semibold";
const TEXT = "m-0 max-w-[340px] text-sm leading-relaxed text-text-2";

export function QueueSkeleton() {
  // 首次加载用居中 spinner，不渲染表格骨架：避免刷新瞬间先闪一层表格网格线。
  return (
    <div
      className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-surface shadow-panel"
      aria-busy="true"
      aria-label="队列加载中"
    >
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-border border-t-accent motion-reduce:animate-none"
      />
      <p className="m-0 text-sm text-text-3">正在同步队列…</p>
    </div>
  );
}

export function QueueEmpty({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className={STATE}>
      <span className={`${ICON} bg-accent-soft text-accent`}>
        <Check size={20} strokeWidth={1.8} aria-hidden="true" />
      </span>
      <h2 className={TITLE}>队列已清空</h2>
      <p className={TEXT}>当前没有等待中的会话。保持在线，点击刷新即可查看新请求。</p>
      <Button variant="secondary" size="sm" className="mt-1" onClick={onRefresh}>
        手动刷新
      </Button>
    </div>
  );
}

export function QueueError({
  message,
  code,
  onRetry,
  retrying,
}: {
  message: string;
  code?: string;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div className={STATE} role="alert">
      <span className={`${ICON} bg-danger-soft text-danger`}>
        <CircleAlert size={20} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <h2 className={TITLE}>队列加载失败</h2>
      <p className={TEXT}>{message}</p>
      <span className="text-xs tabular-nums text-text-3">{code ?? "QUEUE_UNAVAILABLE"}</span>
      <Button variant="primary" size="sm" className="mt-1" onClick={onRetry} disabled={retrying}>
        {retrying ? "重试中…" : "重试"}
      </Button>
    </div>
  );
}

export function DeniedState({ onLogout }: { onLogout: () => void }) {
  return (
    <div className={`${STATE} m-auto max-w-[440px]`} role="alert">
      <span className={`${ICON} bg-surface-2 text-text-2`}>
        <LockKeyhole size={19} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <h2 className={TITLE}>无权访问该队列</h2>
      <p className={TEXT}>当前账号不是坐席角色。如需处理会话，请先联系管理员开通权限。</p>
      <Button variant="secondary" size="sm" className="mt-1" onClick={onLogout}>
        返回登录
      </Button>
    </div>
  );
}

export function PageLoading({ label = "加载中…" }: { label?: string }) {
  return (
    <main className="grid min-h-dvh place-items-center bg-bg font-sans text-sm text-text-3">
      <p aria-busy="true" className="m-0 flex items-center gap-2">
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-border border-t-accent motion-reduce:animate-none"
        />
        {label}
      </p>
    </main>
  );
}
