"use client";

type WorkspaceNavProps = {
  agentName: string;
  roleLabel: string;
  queueCount: number;
  busy?: boolean;
  onLogout: () => void;
};

const ICON_QUEUE = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M2.5 4h11M2.5 8h11M2.5 12h7"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);
const ICON_CHAT = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M3 4.2A2.2 2.2 0 0 1 5.2 2h5.6A2.2 2.2 0 0 1 13 4.2v3.1a2.2 2.2 0 0 1-2.2 2.2H7l-2.7 2.2v-2.2A2.2 2.2 0 0 1 3 7.3V4.2Z"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinejoin="round"
    />
  </svg>
);
const ICON_USER = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="5" r="2.4" stroke="currentColor" strokeWidth="1.4" />
    <path
      d="M3.5 13c.5-2.4 2.2-3.6 4.5-3.6s4 1.2 4.5 3.6"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
    />
  </svg>
);
const ICON_ORDER = (
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
);
const ICON_SETTINGS = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M9.2 2.6a1.8 1.8 0 0 0-2.4 0L6.2 3.2l-.9-.1a1.8 1.8 0 0 0-2 2l.1.9-.6.6a1.8 1.8 0 0 0 0 2.4l.6.6-.1.9a1.8 1.8 0 0 0 2 2l.9-.1.6.6a1.8 1.8 0 0 0 2.4 0l.6-.6.9.1a1.8 1.8 0 0 0 2-2l-.1-.9.6-.6a1.8 1.8 0 0 0 0-2.4l-.6-.6.1-.9a1.8 1.8 0 0 0-2-2l-.9.1-.6-.6Z"
      stroke="currentColor"
      strokeWidth="1.3"
    />
    <circle cx="8" cy="8" r="1.8" stroke="currentColor" strokeWidth="1.3" />
  </svg>
);

const ITEM = "flex h-[38px] items-center gap-2.5 rounded-[9px] px-2.5 text-sm";
const GROUP = "px-2.5 pb-2 text-xs tracking-[0.14em] text-paper/35";

export function WorkspaceNav({
  agentName,
  roleLabel,
  queueCount,
  busy = false,
  onLogout,
}: WorkspaceNavProps) {
  return (
    <aside
      aria-label="工作台导航"
      className="relative hidden min-h-screen w-[224px] shrink-0 flex-col overflow-hidden bg-brand-deep px-3.5 pb-4 pt-5 text-sidebar-ink min-[1024px]:flex"
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -right-36 top-10 h-80 w-80 rounded-full border border-brand-mint/10 shadow-[0_0_0_60px_rgba(158,199,184,0.04)]"
      />

      <div className="relative z-[1] flex items-center gap-2.5 px-2 pb-5 pt-1.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[9px] bg-accent">
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
        <span className="flex flex-col">
          <span className="text-sm font-semibold tracking-[0.12em] text-white">ECHO</span>
          <span className="mt-0.5 text-xs tracking-[0.18em] text-paper/40">CONSOLE</span>
        </span>
      </div>

      <div className={`relative z-[1] ${GROUP}`}>工作区</div>
      <a
        href="/queue"
        aria-current="page"
        className={`${ITEM} relative z-[1] bg-surface/[0.08] font-medium text-white shadow-[inset_2px_0_0_var(--accent)]`}
      >
        {ICON_QUEUE}
        待接入队列
        <span className="ml-auto grid h-[18px] min-w-5 place-items-center rounded-full bg-accent px-1.5 text-xs text-paper">
          {queueCount}
        </span>
      </a>
      <span className={`${ITEM} relative z-[1] text-paper/70`}>
        {ICON_CHAT}
        我的会话
      </span>
      <span className={`${ITEM} relative z-[1] text-paper/35`}>
        {ICON_USER}
        客户
        <span className="ml-auto text-xs text-paper/25">即将开放</span>
      </span>
      <span className={`${ITEM} relative z-[1] text-paper/35`}>
        {ICON_ORDER}
        订单
        <span className="ml-auto text-xs text-paper/25">即将开放</span>
      </span>

      <div className={`${GROUP} relative z-[1] mt-4`}>管理</div>
      <span className={`${ITEM} relative z-[1] text-paper/70`}>{ICON_SETTINGS}设置</span>

      <div className="relative z-[1] mt-auto border-t border-paper/10 pt-3">
        <div className="flex items-center gap-2.5 px-2 py-1.5">
          <span className="grid h-[30px] w-[30px] place-items-center rounded-full bg-avatar-deep text-sm text-presence-ink">
            {agentName.slice(0, 1)}
          </span>
          <span className="min-w-0">
            <span className="block text-xs text-sidebar-ink">{agentName}</span>
            <span className="mt-0.5 flex items-center gap-1.5 text-xs text-paper/45">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-online" />
              在线 · {roleLabel}
            </span>
          </span>
          <button
            className="ml-auto rounded-md border border-paper/20 px-2 py-1 text-xs text-paper/65 hover:border-paper/40 hover:text-white focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50"
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
