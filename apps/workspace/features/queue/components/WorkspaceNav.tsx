"use client";

import styles from "./WorkspaceNav.module.css";

type WorkspaceNavProps = {
  agentName: string;
  roleLabel: string;
  queueCount: number;
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
    <aside className={styles.sidebar} aria-label="工作台导航">
      <div className={styles.logo}>
        <span className={styles.logoMark}>
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path
              d="M4 6.5a7 7 0 0 1 12 0"
              stroke="#eaf4ef"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            <path
              d="M6.2 9.5a4.6 4.6 0 0 1 7.6 0"
              stroke="#9ec7b8"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            <circle cx="10" cy="12.6" r="1.5" fill="#eaf4ef" />
          </svg>
        </span>
        <span>
          <span className={styles.logoName}>ECHO</span>
          <span className={styles.logoSub}>CONSOLE</span>
        </span>
      </div>

      <div className={styles.groupLabel}>工作区</div>
      <a className={`${styles.item} ${styles.active}`} href="/queue" aria-current="page">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path
            d="M2.5 4h11M2.5 8h11M2.5 12h7"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
        待接入队列
        <span className={styles.count}>{queueCount}</span>
      </a>
      <span className={styles.item}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path
            d="M3 4.2A2.2 2.2 0 0 1 5.2 2h5.6A2.2 2.2 0 0 1 13 4.2v3.1a2.2 2.2 0 0 1-2.2 2.2H7l-2.7 2.2v-2.2A2.2 2.2 0 0 1 3 7.3V4.2Z"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
        我的会话
      </span>
      <span className={`${styles.item} ${styles.locked}`}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="5" r="2.4" stroke="currentColor" strokeWidth="1.4" />
          <path
            d="M3.5 13c.5-2.4 2.2-3.6 4.5-3.6s4 1.2 4.5 3.6"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
        </svg>
        客户
        <span className={styles.lock}>即将开放</span>
      </span>
      <span className={`${styles.item} ${styles.locked}`}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path
            d="M3 5.5 8 3l5 2.5v5L8 13l-5-2.5v-5Z"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
          <path
            d="M3 5.5 8 8l5-2.5M8 8v5"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
        订单
        <span className={styles.lock}>即将开放</span>
      </span>

      <div className={styles.groupLabel} style={{ marginTop: 18 }}>
        管理
      </div>
      <span className={styles.item}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path
            d="M9.2 2.6a1.8 1.8 0 0 0-2.4 0L6.2 3.2l-.9-.1a1.8 1.8 0 0 0-2 2l.1.9-.6.6a1.8 1.8 0 0 0 0 2.4l.6.6-.1.9a1.8 1.8 0 0 0 2 2l.9-.1.6.6a1.8 1.8 0 0 0 2.4 0l.6-.6.9.1a1.8 1.8 0 0 0 2-2l-.1-.9.6-.6a1.8 1.8 0 0 0 0-2.4l-.6-.6.1-.9a1.8 1.8 0 0 0-2-2l-.9.1-.6-.6Z"
            stroke="currentColor"
            strokeWidth="1.3"
          />
          <circle cx="8" cy="8" r="1.8" stroke="currentColor" strokeWidth="1.3" />
        </svg>
        设置
      </span>

      <div className={styles.foot}>
        <div className={styles.agent}>
          <span className={styles.avatar} aria-hidden="true">
            {agentName.slice(0, 1)}
          </span>
          <span className={styles.agentText}>
            <span className={styles.agentName}>{agentName}</span>
            <span className={styles.agentMeta}>
              <span className={styles.dot} aria-hidden="true" />
              在线 · {roleLabel}
            </span>
          </span>
          <button
            className={styles.logout}
            type="button"
            onClick={onLogout}
            disabled={busy}
            aria-label="退出登录"
          >
            退出
          </button>
        </div>
      </div>
    </aside>
  );
}
