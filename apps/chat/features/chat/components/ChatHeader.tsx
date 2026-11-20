"use client";

import { Button } from "@/components/ui/Button";

const ECHO_MARK = (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M4 6.5a7 7 0 0 1 12 0"
      stroke="var(--presence-ink)"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
    <path
      d="M6.2 9.5a4.6 4.6 0 0 1 7.6 0"
      stroke="var(--brand-mint)"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
    <circle cx="10" cy="12.6" r="1.5" fill="var(--presence-ink)" />
  </svg>
);

type ChatHeaderProps = {
  customerName: string;
  statusLabel: string;
  dotClass: string;
  chipClass: string;
  closed: boolean;
  closing: boolean;
  busy?: boolean;
  onClose: () => void;
  onLogout: () => void;
};

export function ChatHeader({
  customerName,
  statusLabel,
  dotClass,
  chipClass,
  closed,
  closing,
  busy = false,
  onClose,
  onLogout,
}: ChatHeaderProps) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-border bg-surface px-6 max-[1023px]:px-4">
      <h1 className="sr-only">在线支持</h1>
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-deep">
        {ECHO_MARK}
      </span>
      <span className="flex flex-col max-[767px]:hidden">
        <span className="text-sm font-semibold leading-tight">回声客服</span>
        <span className="mt-0.5 text-[11px] tracking-[0.14em] text-text-3">ECHO CARE</span>
      </span>

      <span
        className={`ml-1 inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium ${chipClass}`}
      >
        <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
        {statusLabel}
      </span>

      <div className="ml-auto flex items-center gap-2">
        <span className="mr-1 max-w-[160px] truncate text-sm text-text-2 max-[767px]:hidden">
          {customerName}
        </span>
        {!closed ? (
          <Button variant="ghost" size="sm" onClick={onClose} disabled={closing}>
            {closing ? "结束中…" : "结束会话"}
          </Button>
        ) : null}
        <Button variant="secondary" size="sm" onClick={onLogout} disabled={busy}>
          退出
        </Button>
      </div>
    </header>
  );
}
