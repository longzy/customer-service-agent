"use client";

import { useEffect, useState } from "react";

/**
 * 返回自 `since` 以来经过的整数秒，用于在两次拉取之间本地补秒。
 *
 * 用 `performance.now()` 的差值计算，而不是每次 +1：
 * 后台标签页的 1s 定时器会被浏览器节流，累加会越走越慢；
 * 差值法在回到前台时一次对齐。回到可见状态时也会立即补一次。
 *
 * `since` 为 null（还没有拉到数据）时返回 0。
 */
export function useElapsedSeconds(since: number | null): number {
  const [now, setNow] = useState(() => performance.now());

  useEffect(() => {
    if (since === null) {
      return;
    }
    const tick = () => setNow(performance.now());
    tick();
    const timer = window.setInterval(tick, 1000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        tick();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [since]);

  if (since === null) {
    return 0;
  }
  return Math.max(0, Math.floor((now - since) / 1000));
}
