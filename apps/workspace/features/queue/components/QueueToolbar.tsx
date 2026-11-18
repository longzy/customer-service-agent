"use client";

import type { RefObject } from "react";

import styles from "./QueueToolbar.module.css";

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

const REASONS: Array<{ value: string; label: string }> = [
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
    <div className={styles.toolbar}>
      <div className={styles.tabs} role="tablist" aria-label="队列筛选">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={filter === tab.value}
            className={`${styles.tab} ${filter === tab.value ? styles.active : ""}`}
            onClick={() => onFilter(tab.value)}
          >
            {tab.label}
            <b>{counts[tab.value]}</b>
          </button>
        ))}
      </div>

      <div className={styles.right}>
        <label className={styles.search}>
          <span className={styles.srOnly}>筛选队列内客户</span>
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
          />
        </label>

        <label className={styles.select}>
          <span className={styles.srOnly}>按原因筛选</span>
          <span className={styles.selectText}>原因</span>
          <select value={reason} onChange={(event) => onReason(event.target.value)}>
            {REASONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.select}>
          <span className={styles.srOnly}>排序方式</span>
          <span className={styles.selectText}>排序</span>
          <select value={sort} onChange={(event) => onSort(event.target.value as QueueSort)}>
            <option value="waited">等待最久</option>
            <option value="newest">最新进入</option>
          </select>
        </label>
      </div>
    </div>
  );
}
