"use client";

const STATE =
  "mt-3.5 flex min-h-[360px] flex-col items-center justify-center gap-1.5 rounded-xl border border-border bg-surface p-8 text-center";
const ICON = "mb-0.5 grid h-[38px] w-[38px] place-items-center rounded-full";
const TITLE = "m-0 text-sm font-semibold";
const TEXT = "m-0 max-w-[320px] text-xs leading-[1.6] text-text-2";
const PRIMARY =
  "mt-1.5 h-[30px] rounded-md border border-accent bg-accent px-3 text-xs text-surface focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3";
const SECONDARY =
  "mt-1.5 h-[30px] rounded-md border border-border bg-surface px-3 text-xs text-text focus-visible:outline-none focus-visible:shadow-focus";

export function QueueSkeleton() {
  return (
    <div
      className="mt-3.5 overflow-hidden rounded-xl border border-border bg-surface"
      aria-busy="true"
      aria-label="队列加载中"
    >
      <div className="h-[38px] border-b border-border bg-surface-muted" />
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col style={{ width: 40 }} />
          <col style={{ width: 168 }} />
          <col style={{ width: 70 }} />
          <col style={{ width: 122 }} />
          <col />
          <col style={{ width: 50 }} />
          <col style={{ width: 78 }} />
          <col style={{ width: 76 }} />
        </colgroup>
        <tbody>
          {Array.from({ length: 8 }).map((_, row) => (
            <tr key={row} className="border-b border-line-soft last:border-0">
              {[24, 120, 48, 96, 180, 36, 56, 48].map((width, cell) => (
                <td key={cell} className="h-14 px-2.5">
                  <span
                    className="block h-2 animate-pulse rounded-sm bg-surface-muted"
                    style={{ width }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex h-[38px] items-center bg-surface-quiet px-3 text-xs text-text-3">
        正在同步队列 · 首次加载约 1 秒
      </div>
    </div>
  );
}

export function QueueEmpty({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className={STATE}>
      <span className={`${ICON} bg-accent-soft text-accent`}>
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
      <h2 className={TITLE}>队列已清空</h2>
      <p className={TEXT}>最近 5 分钟没有新的转人工请求。保持在线，新会话会自动出现在这里。</p>
      <button className={SECONDARY} type="button" onClick={onRefresh}>
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
    <div className={STATE} role="alert">
      <span className={`${ICON} bg-danger-soft text-danger`}>
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path
            d="M9 5.2v4.2M9 12.2v.3"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
          <circle cx="9" cy="9" r="6.6" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </span>
      <h2 className={TITLE}>队列加载失败</h2>
      <p className={TEXT}>{message}</p>
      <span className="text-xs tabular-nums text-text-3">QUEUE_UNAVAILABLE</span>
      <button className={PRIMARY} type="button" onClick={onRetry} disabled={retrying}>
        {retrying ? "重试中…" : "重试"}
      </button>
    </div>
  );
}

export function DeniedState({ onLogout }: { onLogout: () => void }) {
  return (
    <div className={STATE} role="alert">
      <span className={`${ICON} bg-bg text-text-2`}>
        <svg width="17" height="17" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <rect
            x="4"
            y="8"
            width="10"
            height="7"
            rx="1.6"
            stroke="currentColor"
            strokeWidth="1.5"
          />
          <path d="M6.4 8V6.2a2.6 2.6 0 0 1 5.2 0V8" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </span>
      <h2 className={TITLE}>无权访问该队列</h2>
      <p className={TEXT}>当前账号不是坐席角色。如需处理会话，请联系管理员开通权限。</p>
      <button className={SECONDARY} type="button" onClick={onLogout}>
        返回登录
      </button>
    </div>
  );
}

export function PageLoading({ label = "加载中…" }: { label?: string }) {
  return (
    <main className="grid min-h-screen place-items-center bg-bg font-sans text-sm text-text-2">
      <p aria-busy="true">{label}</p>
    </main>
  );
}
