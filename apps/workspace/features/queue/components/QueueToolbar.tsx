"use client";

import type { RefObject } from "react";

export type QueueFilter = "all" | "waiting" | "overdue";
export type QueueSort = "waited" | "newest";

type QueueToolbarProps = {
  filter: QueueFilter;
  counts: { all: number; waiting: number; overdue: number };
  reason: string;
  sort: QueueSort;
  query: string;
  onFilter: (filter: QueueFilter) => void;
  onReason: (reason: string) => void;
  onSort: (sort: QueueSort) => void;
  onQuery: (query: string) => void;
  searchRef?: RefObject<HTMLInputElement | null>;
};

const REASONS = [
  { value: "ALL", label: "全部" },
  { value: "CUSTOMER_REQUEST", label: "客户要求转人工" },
  { value: "LOW_CONFIDENCE", label: "AI 置信度不足" },
  { value: "OUT_OF_SCOPE", label: "超出 AI 处理范围" },
  { value: "MODEL_UNAVAILABLE", label: "模型不可用" },
];

const TABS: Array<{ value: QueueFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "waiting", label: "等待中" },
  { value: "overdue", label: "已超时" },
];

const TAB_BASE =
  "relative flex items-center gap-1.5 bg-transparent px-0 pb-2.5 pt-2 text-sm text-text-2 focus-visible:outline-none focus-visible:shadow-focus";
const TAB_ACTIVE =
  "font-semibold text-accent after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded after:bg-accent";

const SELECT =
  "flex h-[30px] items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-sm text-text-2 focus-within:border-accent focus-within:shadow-focus";

export function QueueToolbar({
  filter,
  counts,
  reason,
  sort,
  query,
  onFilter,
  onReason,
  onSort,
  onQuery,
  searchRef,
}: QueueToolbarProps) {
  return (
    <div className="mt-4.5 flex flex-wrap items-center gap-4 border-b border-border">
      <div className="flex gap-5" role="tablist" aria-label="队列筛选">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={filter === tab.value}
            className={`${TAB_BASE} ${filter === tab.value ? TAB_ACTIVE : ""}`}
            onClick={() => onFilter(tab.value)}
          >
            {tab.label}
            <b className="tabular-nums">{counts[tab.value]}</b>
          </button>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2 pb-2">
        <label className="flex h-[30px] min-w-[172px] items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-text-3 focus-within:border-accent focus-within:shadow-focus max-[1023px]:min-w-[150px]">
          <span className="sr-only">筛选队列内客户</span>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
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
            placeholder="筛选队列内客户"
            aria-label="筛选队列内客户"
            className="min-w-0 flex-1 bg-transparent text-sm text-text outline-none placeholder:text-text-3"
          />
        </label>

        <label className={SELECT}>
          <span className="sr-only">按原因筛选</span>
          <span>原因</span>
          <select
            value={reason}
            onChange={(event) => onReason(event.target.value)}
            className="max-w-[150px] border-0 bg-transparent text-sm text-text outline-none"
          >
            {REASONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className={SELECT}>
          <span className="sr-only">排序方式</span>
          <span>排序</span>
          <select
            value={sort}
            onChange={(event) => onSort(event.target.value as QueueSort)}
            className="border-0 bg-transparent text-sm text-text outline-none"
          >
            <option value="waited">等待最久</option>
            <option value="newest">最新进入</option>
          </select>
        </label>
      </div>
    </div>
  );
}
