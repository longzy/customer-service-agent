"use client";

import { Clock, MessageCircle, ShieldCheck } from "lucide-react";

import { EchoWaves } from "@/components/ui/EchoWaves";

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
      stroke="var(--presence-ink)"
      strokeWidth="1.6"
      strokeLinecap="round"
    />
    <circle cx="10" cy="12.6" r="1.5" fill="var(--presence-ink)" />
  </svg>
);

const POINTS = [
  { icon: Clock, text: "服务时间 9:00 – 22:00" },
  { icon: MessageCircle, text: "非服务时间可留言，次日优先处理" },
  { icon: ShieldCheck, text: "对话内容加密传输，仅用于本次服务" },
];

export function LoginBrand() {
  return (
    <aside
      aria-label="回声客服"
      className="relative flex flex-col overflow-hidden bg-brand-tint px-10 py-12 max-[1023px]:flex-row max-[1023px]:items-center max-[1023px]:px-6 max-[1023px]:py-5"
    >
      {/* 品牌回声：右下角同心弧，定位由容器决定（ui-spec 3.1）。 */}
      <div className="pointer-events-none absolute inset-0 text-text">
        <EchoWaves className="h-full w-full" />
      </div>

      <div className="relative z-[1] flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-deep">
          {ECHO_MARK}
        </span>
        <span className="flex flex-col">
          <span className="text-lg font-semibold tracking-[-0.01em]">回声 ECHO</span>
          <span className="mt-0.5 text-xs tracking-[0.16em] text-text-3">CUSTOMER CARE</span>
        </span>
      </div>

      <div className="relative z-[1] mt-14 max-[1023px]:hidden">
        <span className="inline-flex h-7 items-center gap-2 rounded-full border border-border bg-surface px-3 text-xs font-medium text-text-2">
          <span
            aria-hidden="true"
            className="h-1.5 w-1.5 rounded-full bg-online shadow-[0_0_0_3px_var(--halo-online)]"
          />
          真人客服在线
        </span>
        <h1 className="mt-6 max-w-[320px] text-[40px] font-semibold leading-[1.15] tracking-[-0.03em]">
          有问题，
          <br />
          <span className="text-text-3">随时说。</span>
        </h1>
        <p className="mt-5 max-w-[300px] text-sm leading-[1.8] text-text-2">
          订单、退换、物流，都可以直接问。需要真人时，随时为你转接。
        </p>
      </div>

      <ul className="relative z-[1] mt-9 flex list-none flex-col gap-3 p-0 text-sm text-text-2 max-[1023px]:hidden">
        {POINTS.map((point) => (
          <li key={point.text} className="flex items-center gap-2.5">
            <point.icon
              size={15}
              strokeWidth={1.7}
              aria-hidden="true"
              className="shrink-0 text-text-3"
            />
            {point.text}
          </li>
        ))}
      </ul>

      <div className="relative z-[1] mt-auto text-xs leading-[1.9] text-text-3 max-[1023px]:hidden">
        回声 ECHO · 客户服务中心
      </div>
    </aside>
  );
}
