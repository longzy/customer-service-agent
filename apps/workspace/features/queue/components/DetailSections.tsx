"use client";

import { LockKeyhole } from "lucide-react";

import type { QueueItem } from "../types";

export function DetailSections({ item }: { item: QueueItem }) {
  return (
    <>
      <section className="flex flex-col gap-2">
        <h2 className="m-0 text-xs font-medium text-text-3">最后一条消息</h2>
        <div className="rounded-xl border border-border bg-surface-2 px-3 py-2.5">
          <span className="text-xs font-medium text-text-2">{item.customer_display_name}</span>
          <p className="mt-1 text-sm leading-relaxed text-text">
            {item.last_message || "（无客户消息）"}
          </p>
        </div>
        <p className="m-0 flex items-center gap-1.5 text-xs text-text-3">
          <LockKeyhole size={12} strokeWidth={1.6} aria-hidden="true" />
          敏感信息已隐藏
        </p>
      </section>

      <section className="flex flex-col gap-1.5 rounded-xl border border-border bg-surface px-3.5 py-3 text-xs leading-relaxed text-text-2">
        <h2 className="m-0 text-sm font-semibold text-text">领取规则</h2>
        <span>
          <b className="font-semibold text-text">领取后进入会话页</b>
          ，可查看完整交接单与上下文。
        </span>
        <span>同一会话仅一名坐席可领取；冲突会刷新队列。</span>
      </section>
    </>
  );
}
