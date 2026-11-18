"use client";

import type { RefObject } from "react";

import styles from "./WorkspaceHeader.module.css";

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
      <header className={styles.topbar}>
        <div className={styles.crumb}>
          工作台<span>/</span>
          <b>待接入队列</b>
        </div>
        <label className={styles.search}>
          <span className={styles.srOnly}>搜索客户、账号或会话 ID</span>
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
          />
          <kbd>⌘K</kbd>
        </label>
        <div className={styles.topRight}>
          <span className={styles.iconBtn} aria-hidden="true">
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
          <span className={styles.statusPill}>
            <span className={styles.dot} aria-hidden="true" />
            在线
          </span>
          <span className={styles.topAvatar} aria-hidden="true">
            {agentName.slice(0, 1)}
          </span>
        </div>
      </header>

      <div className={styles.pageHead}>
        <div>
          <h1>待接入队列</h1>
          <p className={styles.sub}>
            共 {total} 个会话在等待，{overdue} 个已超过 5 分钟 · 按等待时长（最久优先）
          </p>
        </div>
        <div className={styles.headActions}>
          <span className={styles.actionNote}>批量领取需服务端支持</span>
          <button className={styles.button} type="button" disabled>
            批量领取 (0)
          </button>
          <button className={styles.button} type="button" onClick={onRefresh} disabled={loading}>
            刷新
          </button>
          <span className={styles.auto}>自动刷新 30s</span>
        </div>
      </div>
    </>
  );
}
