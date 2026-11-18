"use client";

import type { QueueItem } from "../types";

export function DetailSections({ item }: { item: QueueItem }) {
  return (
    <>
      <div className="flex flex-col gap-2">
        <div className="flex items-center text-xs font-semibold text-text-2">
          <span>最后一条消息</span>
          <span className="ml-auto text-xs font-normal text-text-3">已脱敏</span>
        </div>
        <div className="rounded-[9px] border border-line-soft bg-surface-soft px-2.5 py-2">
          <div className="flex items-center text-xs text-text-3">
            <span className="font-semibold text-avatar-strong-ink">
              {item.customer_display_name}
            </span>
          </div>
          <p className="mt-1 text-xs leading-[1.55] text-text">
            {item.last_message || "（无客户消息）"}
          </p>
        </div>
        <div className="flex items-center gap-1.5 rounded-[7px] bg-bg px-2.5 py-[7px] text-xs text-text-3">
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true">
            <rect
              x="2"
              y="5"
              width="8"
              height="5.5"
              rx="1.2"
              stroke="currentColor"
              strokeWidth="1.2"
            />
            <path d="M4 5V3.8a2 2 0 0 1 4 0V5" stroke="currentColor" strokeWidth="1.2" />
          </svg>
          手机号、邮箱、身份证号已隐藏
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center text-xs font-semibold text-text-2">
          <span>完整上下文</span>
          <span className="ml-auto text-xs font-normal text-text-3">领取后可见</span>
        </div>
        <div className="flex flex-col gap-1.5 rounded-[9px] border border-line-soft bg-surface-soft px-2.5 py-2 text-xs leading-[1.6] text-text-2">
          <b className="font-semibold text-text">领取后进入会话页</b>
          <span>完整交接单由后续 F-08 承接。</span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 rounded-[9px] border border-line-soft bg-surface-soft px-2.5 py-2 text-xs leading-[1.6] text-text-2">
        <b className="font-semibold text-text">领取规则</b>
        <span>同一会话仅一名坐席可领取；冲突返回 409 并刷新队列。</span>
        <span>领取后锁定 8 小时，可在「我的会话」中继续。</span>
      </div>
    </>
  );
}
