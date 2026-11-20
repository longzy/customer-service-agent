"use client";

import { Avatar } from "@heroui/react";
import { List, LogOut } from "lucide-react";

type WorkspaceNavProps = {
  agentName: string;
  roleLabel: string;
  queueCount?: number;
  busy?: boolean;
  onLogout: () => void;
};

export function WorkspaceNav({
  agentName,
  roleLabel,
  queueCount,
  busy = false,
  onLogout,
}: WorkspaceNavProps) {
  return (
    <aside
      aria-label="工作台导航"
      className="hidden w-[232px] shrink-0 flex-col border-r border-border bg-surface px-3 py-4 min-[1024px]:flex max-[1279px]:w-[208px]"
    >
      <div className="flex items-center gap-2.5 px-2 pb-6 pt-1">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-deep">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path
              d="M4 6.5a7 7 0 0 1 12 0"
              stroke="var(--presence-ink)"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            <path
              d="M6.2 9.5a4.6 4.6 0 0 1 7.6 0"
              stroke="var(--presence-ink)"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            <circle cx="10" cy="12.6" r="1.5" fill="var(--presence-ink)" />
          </svg>
        </span>
        <span className="flex flex-col">
          <span className="text-sm font-semibold leading-tight">ECHO</span>
          <span className="mt-0.5 text-[11px] tracking-[0.16em] text-text-3">CONSOLE</span>
        </span>
      </div>

      <p className="m-0 px-3 pb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-text-3">
        工作区
      </p>
      <a
        href="/queue"
        aria-current="page"
        className="flex h-10 items-center gap-2.5 rounded-lg bg-accent-soft px-3 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-line focus-visible:outline-none focus-visible:shadow-focus"
      >
        <List size={16} strokeWidth={1.8} aria-hidden="true" />
        待接入队列
        {queueCount === undefined ? null : (
          <span className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1.5 text-[11px] font-semibold tabular-nums text-white">
            {queueCount}
          </span>
        )}
      </a>
      <p className="m-0 mt-3 px-3 text-[11px] leading-relaxed text-text-3">
        新会话会出现在队列中；领取后进入会话页回复客户。
      </p>

      <div className="mt-auto border-t border-line-soft pt-3">
        <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
          <Avatar className="h-9 w-9 shrink-0 bg-accent-soft text-xs text-accent-ink">
            <Avatar.Fallback>{agentName.slice(0, 1)}</Avatar.Fallback>
          </Avatar>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-text">{agentName}</span>
            <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-text-3">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-online" />
              在线 · {roleLabel}
            </span>
          </span>
          <button
            className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-text-3 transition-colors hover:bg-surface-2 hover:text-text-2 focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50"
            type="button"
            onClick={onLogout}
            disabled={busy}
            aria-label="退出登录"
            title="退出登录"
          >
            <LogOut size={15} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
