"use client";

import brandStyles from "./LoginBrand.module.css";

const isDev = process.env.NODE_ENV !== "production";

export function LoginBrand() {
  return (
    <aside className={brandStyles.brand} aria-label="ECHO 工作台">
      <div className={brandStyles.logo}>
        <span className={brandStyles.logoMark}>
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
        <div className={brandStyles.logoText}>
          <span className={brandStyles.logoName}>ECHO</span>
          <span className={brandStyles.logoSub}>CONSOLE</span>
        </div>
      </div>

      <h1 className={brandStyles.headline}>
        客服工作台
        <span>登录后开始接待。</span>
      </h1>
      <p className={brandStyles.lede}>
        待接入队列、会话详情与完整交接记录。登录后你可以看到本租户的客户会话，所有操作都会被审计。
      </p>

      <div className={brandStyles.facts}>
        <div>
          <div className={brandStyles.factValue}>12</div>
          <div className={brandStyles.factLabel}>当前等待</div>
        </div>
        <div>
          <div className={brandStyles.factValue}>40s</div>
          <div className={brandStyles.factLabel}>平均响应</div>
        </div>
        <div>
          <div className={brandStyles.factValue}>8h</div>
          <div className={brandStyles.factLabel}>会话锁定</div>
        </div>
      </div>

      <div className={brandStyles.brandFoot}>
        <div className={brandStyles.brandMeta}>
          <b>内部系统 · 仅限员工使用</b>
          ECHO CONSOLE v0.1.0
        </div>
        {isDev ? (
          <span className={brandStyles.env}>
            <span className={brandStyles.envSpan} aria-hidden="true" />
            开发环境
          </span>
        ) : null}
      </div>
    </aside>
  );
}
