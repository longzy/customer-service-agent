"use client";

type ChatBrandProps = {
  customerName: string;
  busy?: boolean;
  onLogout: () => void;
};

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
      stroke="var(--brand-mint)"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
    <circle cx="10" cy="12.6" r="1.5" fill="var(--presence-ink)" />
  </svg>
);

export function ChatBrand({ customerName, busy = false, onLogout }: ChatBrandProps) {
  return (
    <aside
      aria-label="回声客服"
      className="relative flex w-[340px] shrink-0 flex-col overflow-hidden bg-brand-deep px-[34px] pb-[30px] pt-[34px] text-paper min-[1024px]:max-[1279px]:w-[300px] max-[1023px]:w-auto max-[1023px]:flex-row max-[1023px]:items-center max-[1023px]:px-4 max-[1023px]:py-3.5"
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-32 -left-28 h-[400px] w-[400px] rounded-full border border-brand-mint/[0.14]"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-32 -left-28 h-[340px] w-[340px] rounded-full border border-brand-mint/[0.10]"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-32 -left-28 h-[280px] w-[280px] rounded-full border border-brand-mint/[0.07]"
      />

      <div className="relative z-[1] flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-accent">
          {ECHO_MARK}
        </span>
        <span className="flex flex-col">
          <span className="text-lg font-semibold tracking-[0.14em]">回声 ECHO</span>
          <span className="mt-0.5 text-xs tracking-[0.22em] text-paper/65">CUSTOMER CARE</span>
        </span>
      </div>

      <h1 className="relative z-[1] mt-16 font-serif text-[44px] font-semibold leading-[1.16] tracking-[0.01em] max-[1023px]:hidden">
        有问题，
        <br />
        <em className="not-italic text-brand-mint">随时说。</em>
      </h1>
      <p className="relative z-[1] mt-5 max-w-[260px] text-sm leading-[1.9] text-paper/65 max-[1023px]:hidden">
        真人客服在工作时间在线。订单、退换、物流，都可以直接问。
      </p>

      <div className="relative z-[1] mt-8 flex items-start gap-3 rounded-xl border border-paper/15 bg-surface/[0.03] p-4 max-[1023px]:hidden">
        <span
          aria-hidden="true"
          className="mt-1 h-2 w-2 shrink-0 rounded-full bg-online shadow-[0_0_0_4px_var(--halo-online)]"
        />
        <div>
          <div className="text-sm font-semibold text-presence-ink">人工客服在线</div>
          <div className="mt-0.5 text-xs text-paper/70">服务时间 9:00 – 22:00</div>
        </div>
      </div>

      <div className="relative z-[1] mt-auto max-[1023px]:ml-auto">
        <p className="mb-3 text-xs leading-[1.9] text-paper/65 max-[1023px]:hidden">
          非服务时间可留言，次日优先处理。
          <br />
          对话内容仅用于本次服务。
        </p>
        <div className="flex items-center gap-3 border-t border-paper/15 pt-5 max-[1023px]:border-0 max-[1023px]:pt-0">
          <span className="text-xs text-paper/70">{customerName}</span>
          <button
            className="ml-auto rounded-md border border-paper/20 px-2.5 py-1 text-xs text-paper/70 hover:border-paper/40 hover:text-paper focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50"
            type="button"
            onClick={onLogout}
            disabled={busy}
          >
            退出
          </button>
        </div>
      </div>
    </aside>
  );
}
