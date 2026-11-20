"use client";

import { Kbd } from "@heroui/react";

const KBD = "mr-1 h-5 px-1.5 text-[11px]";

export function QueueKeyBar() {
  return (
    <div className="mt-3 flex min-h-[36px] shrink-0 flex-wrap items-center gap-4 px-1 py-2 text-xs text-text-3 max-[767px]:hidden">
      <span>
        <Kbd className={KBD}>J</Kbd>
        <Kbd className={KBD}>K</Kbd> 选择
      </span>
      <span>
        <Kbd className={KBD}>Enter</Kbd> 领取
      </span>
      <span>
        <Kbd className={KBD}>⌘K</Kbd> 搜索
      </span>
      <span>
        <Kbd className={KBD}>?</Kbd> 快捷键
      </span>
    </div>
  );
}
