"use client";

import { useEffect, type RefObject } from "react";

import type { QueueItem } from "../types";

type Options = {
  visible: QueueItem[];
  selectedId: string | null;
  selected: QueueItem | null;
  searchRef: RefObject<HTMLInputElement | null>;
  onSelect: (id: string | null) => void;
  onClaim: (item: QueueItem) => void;
  onNotice: (message: string) => void;
};

/** 队列键盘流：J/K 选择、Enter 领取、⌘K 搜索、Esc 关闭、? 提示。 */
export function useQueueKeyboard({
  visible,
  selectedId,
  selected,
  searchRef,
  onSelect,
  onClaim,
  onNotice,
}: Options) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement;

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (typing) {
        if (event.key === "Escape") {
          target.blur();
        }
        return;
      }
      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        const index = visible.findIndex((item) => item.handoff_id === selectedId);
        const next = visible[Math.min(index + 1, visible.length - 1)];
        if (next) onSelect(next.handoff_id);
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        const index = visible.findIndex((item) => item.handoff_id === selectedId);
        const next = visible[Math.max(index - 1, 0)];
        if (next) onSelect(next.handoff_id);
      } else if (event.key === "Enter" && selected) {
        // 焦点在按钮/链接上时，Enter 应触发该控件本身，不能再领取一次。
        if (target instanceof Element && target.closest('button, a, [role="button"]')) {
          return;
        }
        event.preventDefault();
        onClaim(selected);
      } else if (event.key === "Escape") {
        onSelect(null);
      } else if (event.key === "?") {
        onNotice("快捷键：J/K 选择 · Enter 领取 · ⌘K 搜索 · Esc 关闭");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClaim, onNotice, onSelect, searchRef, selected, selectedId, visible]);
}
