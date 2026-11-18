"use client";

import type { RefObject } from "react";

type WorkspaceHeaderProps = {
  agentName: string;
  total: number;
  overdue: number;
  loading: boolean;
  query: string;
  searchRef: RefObject<HTMLInputElement | null>;
  onQuery: (value: string) => void;
  onRefresh: () => void;
};

const BUTTON =
  "h-8 rounded-md border border-border bg-surface px-3 text-sm text-text hover:border-border-strong focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-text-3";

export function WorkspaceHeader({
  agentName,
  total,
  overdue,
  loading,
  query,
  searchRef,
  onQuery,
  onRefresh,
}: WorkspaceHeaderProps) {
  return (
    <>
      <header className="flex h-[60px] shrink-0 items-center gap-3 border-b border-border bg-surface px-6 max-[1023px]:px-4">
        <div className="whitespace-nowrap text-sm text-text-3">
          工作台<span className="mx-1.5 text-border-strong">/</span>
          <b className="font-medium text-text">待接入队列</b>
        </div>

        <label className="ml-4.5 flex h-8 w-[300px] items-center gap-2 rounded-md border border-border bg-bg px-2.5 text-text-3 focus-within:border-accent focus-within:shadow-focus max-[1279px]:w-[240px] max-[1023px]:ml-2 max-[1023px]:w-[200px] max-[767px]:hidden">
          <span className="sr-only">搜索客户、账号或会话 ID</span>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.4" />
            <path
              d="m10.5 10.5 2.5 2.5"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
          <input
            ref={searchRef}
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="搜索客户、账号或会话 ID"
            aria-label="搜索客户、账号或会话 ID"
            className="min-w-0 flex-1 bg-transparent text-sm text-text outline-none placeholder:text-text-3"
          />
          <kbd className="rounded-sm border border-border border-b-2 bg-surface px-1 text-xs text-text-2">
            ⌘K
          </kbd>
        </label>

        <div className="ml-auto flex items-center gap-3.5">
          <span
            className="grid h-[30px] w-[30px] place-items-center rounded-md text-text-2 max-[767px]:hidden"
            aria-hidden="true"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M8 2a4 4 0 0 1 4 4v2.4l1 1.6H3l1-1.6V6a4 4 0 0 1 4-4Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
              />
              <path
                d="M6.4 12a1.6 1.6 0 0 0 3.2 0"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </span>
          <span className="inline-flex h-[26px] items-center gap-1.5 rounded-full bg-accent-soft px-2.5 text-xs font-medium text-accent-ink">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-success" />
            在线
          </span>
          <span
            className="grid h-[30px] w-[30px] place-items-center rounded-full bg-brand-deep text-sm text-presence-ink"
            aria-hidden="true"
          >
            {agentName.slice(0, 1)}
          </span>
        </div>
      </header>

      <div className="mt-[22px] flex items-end gap-3.5 px-6 max-[1023px]:flex-col max-[1023px]:items-start max-[1023px]:gap-2.5 max-[1023px]:px-4">
        <div>
          <h1 className="m-0 text-[21px] font-semibold tracking-[-0.01em]">待接入队列</h1>
          <p className="mt-1 text-sm text-text-2">
            共 {total} 个会话在等待，{overdue} 个已超过 5 分钟 · 按等待时长（最久优先）
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2 max-[1023px]:ml-0">
          <span className="text-xs text-text-3 max-[1023px]:hidden">批量领取需服务端支持</span>
          <button className={BUTTON} type="button" disabled>
            批量领取 (0)
          </button>
          <button className={BUTTON} type="button" onClick={onRefresh} disabled={loading}>
            刷新
          </button>
          <span className="text-xs text-text-3 max-[1023px]:hidden">自动刷新 30s</span>
        </div>
      </div>
    </>
  );
}
