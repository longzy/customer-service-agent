"use client";

import brandStyles from "./LoginBrand.module.css";

export function LoginBrand() {
  return (
    <aside className={brandStyles.brand} aria-label="回声客服">
      <div className={brandStyles.logo}>
        <span className={brandStyles.logoMark}>
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
        <div className={brandStyles.logoText}>
          <span className={brandStyles.logoName}>回声 ECHO</span>
          <span className={brandStyles.logoSub}>CUSTOMER CARE</span>
        </div>
      </div>

      <h1 className={brandStyles.headline}>
        有问题，
        <br />
        <em>随时说。</em>
      </h1>
      <p className={brandStyles.lede}>
        真人客服在工作时间在线，平均 40 秒接通。订单、退换、物流，都可以直接问。
      </p>

      <div className={brandStyles.presence}>
        <span className={brandStyles.dot} />
        <div>
          <div className={brandStyles.presenceTitle}>人工客服在线</div>
          <div className={brandStyles.presenceMeta}>服务时间 9:00 – 22:00 · 平均 40 秒接通</div>
        </div>
      </div>

      <div className={brandStyles.brandFoot}>
        <strong>服务时间 9:00 – 22:00</strong>
        非服务时间可留言，次日优先处理。
        <br />
        对话内容仅用于本次服务。
      </div>
    </aside>
  );
}
