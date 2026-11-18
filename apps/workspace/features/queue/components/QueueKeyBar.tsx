"use client";

const KBD = "mr-1 rounded-sm border border-border border-b-2 bg-surface px-1 text-xs text-text-2";

export function QueueKeyBar() {
  return (
    <div className="mt-auto flex min-h-[38px] flex-wrap items-center gap-3.5 px-1 py-3 text-xs text-text-3">
      <span>
        <kbd className={KBD}>J</kbd>
        <kbd className={KBD}>K</kbd> 选择
      </span>
      <span>
        <kbd className={KBD}>Enter</kbd> 领取
      </span>
      <span>
        <kbd className={KBD}>⌘K</kbd> 搜索
      </span>
      <span>
        <kbd className={KBD}>?</kbd> 快捷键
      </span>
      <span className="flex-1" />
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-success" />
        已连接 · 自动刷新 30s
      </span>
    </div>
  );
}
