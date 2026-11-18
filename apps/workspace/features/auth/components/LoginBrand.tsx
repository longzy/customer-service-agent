"use client";

const ECHO_MARK = (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M4 6.5a7 7 0 0 1 12 0" stroke="#eaf4ef" strokeWidth="1.6" strokeLinecap="round" />
    <path
      d="M6.2 9.5a4.6 4.6 0 0 1 7.6 0"
      stroke="#9ec7b8"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
    <circle cx="10" cy="12.6" r="1.5" fill="#eaf4ef" />
  </svg>
);

const FACTS = [
  { value: "12", label: "当前等待" },
  { value: "40s", label: "平均响应" },
  { value: "8h", label: "会话锁定" },
];

export function LoginBrand({ isDev }: { isDev: boolean }) {
  return (
    <aside
      aria-label="ECHO 工作台"
      className="relative flex w-[520px] shrink-0 flex-col overflow-hidden bg-brand-deep px-12 pb-[34px] pt-10 text-paper max-[1024px]:w-auto max-[1024px]:flex-row max-[1024px]:items-center max-[1024px]:px-5 max-[1024px]:py-4"
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-40 -top-16 h-[520px] w-[520px] rounded-full border border-brand-mint/15 shadow-[0_0_0_80px_rgba(158,199,184,0.05)]"
      />

      <div className="relative z-[1] flex items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent">
          {ECHO_MARK}
        </span>
        <span className="flex flex-col">
          <span className="text-base font-semibold tracking-[0.14em]">ECHO</span>
          <span className="mt-0.5 text-xs tracking-[0.2em] text-paper/40">CONSOLE</span>
        </span>
      </div>

      <h1 className="relative z-[1] mt-24 text-[40px] font-semibold leading-[1.22] tracking-[-0.01em] max-[1024px]:hidden">
        客服工作台
        <span className="mt-0 block text-brand-mint">登录后开始接待。</span>
      </h1>
      <p className="relative z-[1] mt-5 max-w-[340px] text-base leading-[1.9] text-paper/60 max-[1024px]:hidden">
        待接入队列、会话详情与完整交接记录。登录后你可以看到本租户的客户会话，所有操作都会被审计。
      </p>

      <div className="relative z-[1] mt-9 flex gap-8 max-[1024px]:hidden">
        {FACTS.map((fact) => (
          <div key={fact.label}>
            <div className="text-[22px] font-semibold tabular-nums text-presence-ink">
              {fact.value}
            </div>
            <div className="mt-1 text-xs tracking-[0.04em] text-paper/40">{fact.label}</div>
          </div>
        ))}
      </div>

      <div className="relative z-[1] mt-auto flex items-end gap-3 max-[1024px]:ml-auto max-[1024px]:mt-0">
        <div className="text-xs leading-[1.9] text-paper/40">
          <strong className="block font-medium text-paper/60">内部系统 · 仅限员工使用</strong>
          ECHO CONSOLE v0.1.0
        </div>
        {isDev ? (
          <span className="ml-auto inline-flex h-6 items-center gap-1.5 rounded-full border border-paper/20 px-2.5 text-xs tracking-[0.1em] text-paper/60">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-env-dot" />
            开发环境
          </span>
        ) : null}
      </div>
    </aside>
  );
}
