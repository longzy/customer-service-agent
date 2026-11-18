"use client";

import styles from "./ChatBrand.module.css";

type ChatBrandProps = {
  customerName: string;
  busy?: boolean;
  onLogout: () => void;
};

export function ChatBrand({ customerName, busy = false, onLogout }: ChatBrandProps) {
  return (
    <aside className={styles.brand} aria-label="回声客服">
      <div className={styles.logo}>
        <span className={styles.logoMark}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
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
        <div className={styles.logoText}>
          <span className={styles.logoName}>回声 ECHO</span>
          <span className={styles.logoSub}>CUSTOMER CARE</span>
        </div>
      </div>

      <h1 className={styles.headline}>
        有问题，
        <br />
        <em>随时说。</em>
      </h1>
      <p className={styles.lede}>
        真人客服在工作时间在线，平均 40 秒接通。订单、退换、物流，都可以直接问。
      </p>

      <div className={styles.presence}>
        <span className={styles.dot} />
        <div>
          <div className={styles.presenceTitle}>人工客服在线</div>
          <div className={styles.presenceMeta}>服务时间 9:00 – 22:00 · 平均 40 秒接通</div>
        </div>
      </div>

      <div className={styles.foot}>
        <p className={styles.brandFoot}>
          非服务时间可留言，次日优先处理。
          <br />
          对话内容仅用于本次服务。
        </p>
        <div className={styles.account}>
          <span className={styles.accountName}>{customerName}</span>
          <button className={styles.logout} type="button" onClick={onLogout} disabled={busy}>
            退出
          </button>
        </div>
      </div>
    </aside>
  );
}
