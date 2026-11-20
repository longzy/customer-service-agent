"use client";

import { Clock, LockKeyhole, ShieldCheck } from "lucide-react";

const ECHO_MARK = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
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
);

const POINTS = [
  { icon: Clock, text: "服务时间 9:00 – 22:00" },
  { icon: LockKeyhole, text: "登录后会话锁定 8 小时" },
  { icon: ShieldCheck, text: "领取、回复、关闭全程审计留痕" },
];

export function LoginBrand({ isDev }: { isDev: boolean }) {
  return (
    <aside
      aria-label="ECHO 工作台"
      className="relative flex flex-col overflow-hidden bg-brand-tint px-10 py-12 max-[1023px]:flex-row max-[1023px]:items-center max-[1023px]:px-6 max-[1023px]:py-5"
    >
      {/* 品牌声波：从右上角向外扩散，只做背景层次，不承载信息 */}
      <svg
        aria-hidden="true"
        className="pointer-events-none absolute -right-32 -top-32 h-[460px] w-[460px] text-text opacity-[0.045]"
        viewBox="0 0 200 200"
        fill="none"
      >
        <path
          d="M8 68a92 92 0 0 0 184 0"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M38 68a62 62 0 0 0 124 0"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M68 68a32 32 0 0 0 64 0"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="100" cy="60" r="4" fill="currentColor" />
      </svg>

      <div className="relative z-[1] flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-deep">
          {ECHO_MARK}
        </span>
        <span className="flex flex-col">
          <span className="text-lg font-semibold tracking-[-0.01em]">ECHO</span>
          <span className="mt-0.5 text-xs tracking-[0.16em] text-text-3">CONSOLE</span>
        </span>
      </div>

      <div className="relative z-[1] mt-14 max-[1023px]:hidden">
        <span className="inline-flex h-7 items-center gap-2 rounded-full border border-border bg-surface px-3 text-xs font-medium text-text-2">
          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-text-3" />
          内部系统 · 仅限员工
        </span>
        <h1 className="mt-6 max-w-[340px] text-[40px] font-semibold leading-[1.15] tracking-[-0.03em]">
          客服工作台
          <br />
          <span className="text-text-3">登录后开始接待。</span>
        </h1>
        <p className="mt-5 max-w-[340px] text-sm leading-[1.8] text-text-2">
          待接入队列、会话详情与完整交接记录。所有操作都会被记录，用于安全追溯。
        </p>
      </div>

      <ul className="relative z-[1] mt-9 flex list-none flex-col gap-3 p-0 text-sm text-text-2 max-[1023px]:hidden">
        {POINTS.map((point) => (
          <li key={point.text} className="flex items-center gap-2.5">
            <point.icon
              size={15}
              strokeWidth={1.7}
              aria-hidden="true"
              className="shrink-0 text-text-3"
            />
            {point.text}
          </li>
        ))}
      </ul>

      <div className="relative z-[1] mt-auto flex items-end gap-3 max-[1023px]:ml-auto max-[1023px]:mt-0">
        <div className="text-xs leading-[1.9] text-text-3 max-[1023px]:hidden">
          ECHO CONSOLE v0.1.0
        </div>
        <span className="ml-auto inline-flex h-6 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 text-xs text-text-2">
          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-env-dot" />
          {isDev ? "开发环境" : "生产环境"}
        </span>
      </div>
    </aside>
  );
}
