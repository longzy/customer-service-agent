"use client";

import styles from "./QueueStates.module.css";

export function QueueSkeleton() {
  return (
    <div className={styles.card} aria-busy="true" aria-label="队列加载中">
      <div className={styles.skeletonHead} />
      {Array.from({ length: 8 }).map((_, index) => (
        <div className={styles.skeletonRow} key={index}>
          <span className={styles.bar} style={{ width: 120 }} />
          <span className={styles.bar} style={{ width: 48 }} />
          <span className={styles.bar} style={{ width: 96 }} />
          <span className={styles.bar} style={{ width: 180 }} />
          <span className={styles.bar} style={{ width: 44 }} />
        </div>
      ))}
      <div className={styles.skeletonNote}>正在同步队列 · 首次加载约 1 秒</div>
    </div>
  );
}

export function QueueEmpty({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className={styles.stateCard}>
      <span className={`${styles.icon} ${styles.iconGreen}`}>
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path
            d="M4 9.2 7.2 12.4 14 5.6"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <h2 className={styles.stateTitle}>队列已清空</h2>
      <p className={styles.stateText}>
        最近 5 分钟没有新的转人工请求。保持在线，新会话会自动出现在这里。
      </p>
      <button className={styles.secondaryButton} type="button" onClick={onRefresh}>
        手动刷新
      </button>
    </div>
  );
}

export function QueueError({
  message,
  onRetry,
  retrying,
}: {
  message: string;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div className={styles.stateCard} role="alert">
      <span className={`${styles.icon} ${styles.iconRed}`}>
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path d="M9 5.2v4.2M9 12.2v.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="9" cy="9" r="6.6" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </span>
      <h2 className={styles.stateTitle}>队列加载失败</h2>
      <p className={styles.stateText}>{message}</p>
      <span className={styles.code}>QUEUE_UNAVAILABLE</span>
      <button className={styles.primaryButton} type="button" onClick={onRetry} disabled={retrying}>
        {retrying ? "重试中…" : "重试"}
      </button>
    </div>
  );
}

export function DeniedState({ onLogout }: { onLogout: () => void }) {
  return (
    <div className={styles.stateCard} role="alert">
      <span className={`${styles.icon} ${styles.iconGrey}`}>
        <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <rect x="4" y="8" width="10" height="7" rx="1.6" stroke="currentColor" strokeWidth="1.5" />
          <path d="M6.4 8V6.2a2.6 2.6 0 0 1 5.2 0V8" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </span>
      <h2 className={styles.stateTitle}>无权访问该队列</h2>
      <p className={styles.stateText}>当前账号不是坐席角色。如需处理会话，请联系管理员开通权限。</p>
      <button className={styles.secondaryButton} type="button" onClick={onLogout}>
        返回登录
      </button>
    </div>
  );
}

export function PageLoading({ label = "加载中…" }: { label?: string }) {
  return (
    <main className={styles.pageLoading}>
      <p aria-busy="true">{label}</p>
    </main>
  );
}
