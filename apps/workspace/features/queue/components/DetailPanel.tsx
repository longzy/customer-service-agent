"use client";

import { Avatar, Drawer } from "@heroui/react";

import { Button } from "@/components/ui/Button";

import type { QueueItem } from "../types";

import { DetailSections } from "./DetailSections";
import { formatWait, isOverdue } from "./QueueTable";

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
};

type DetailPanelProps = {
  item: QueueItem | null;
  open: boolean;
  claiming: boolean;
  disabled: boolean;
  onClaim: () => void;
  onClose: () => void;
};

const METRIC_LABEL = "block text-xs text-text-3";
const METRIC_VALUE = "mt-1 block text-sm font-semibold tabular-nums";

export function DetailPanel({
  item,
  open,
  claiming,
  disabled,
  onClaim,
  onClose,
}: DetailPanelProps) {
  return (
    <Drawer
      isOpen={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      {/* Backdrop 必须包住 Content：写成自闭合的独立遮罩时，抽屉关闭只卸载 Content，
           backdrop 会留在最上层挡住整页点击（2026-11-20 修复）。 */}
      <Drawer.Backdrop>
        <Drawer.Content
          placement="right"
          className="[--drawer-enter-duration:200ms] [--drawer-exit-duration:200ms]"
        >
          <Drawer.Dialog
            aria-label="会话详情"
            className="w-[380px] gap-5 border-l border-border bg-surface px-6 py-5 max-[1279px]:w-[340px]"
          >
            <div className="flex items-center gap-3">
              <h2 className="m-0 text-base font-semibold">会话详情</h2>
              <Drawer.CloseTrigger aria-label="关闭详情" className="ml-auto" />
            </div>

            <Drawer.Body className="flex flex-col gap-5 overflow-y-auto p-0">
              {item ? (
                <>
                  <div className="flex items-center gap-3">
                    <Avatar className="h-11 w-11 shrink-0 bg-accent-soft text-base font-medium text-accent-ink">
                      <Avatar.Fallback>{item.customer_display_name.slice(0, 1)}</Avatar.Fallback>
                    </Avatar>
                    <span className="min-w-0">
                      <span className="block truncate text-base font-semibold">
                        {item.customer_display_name}
                      </span>
                      <span className="mt-1 block truncate text-xs text-text-3">
                        {item.customer_username} · 会话 {item.conversation_id.slice(0, 8)}
                      </span>
                    </span>
                  </div>

                  <div className="grid grid-cols-[1fr_1.25fr_1fr] divide-x divide-border overflow-hidden rounded-xl border border-border bg-surface-2">
                    <div className="min-w-0 px-3 py-3">
                      <span className={METRIC_LABEL}>等待</span>
                      <span className={`${METRIC_VALUE} ${isOverdue(item) ? "text-danger" : ""}`}>
                        {formatWait(item.waiting_seconds)}
                      </span>
                    </div>
                    <div className="min-w-0 px-3 py-3">
                      <span className={METRIC_LABEL}>转人工原因</span>
                      <span className="mt-1 block text-xs leading-snug text-text">
                        {REASON_LABEL[item.reason] ?? item.reason}
                      </span>
                    </div>
                    <div className="min-w-0 px-3 py-3">
                      <span className={METRIC_LABEL}>订单</span>
                      <span className={METRIC_VALUE}>{item.order_count}</span>
                    </div>
                  </div>

                  <DetailSections item={item} />
                </>
              ) : null}
            </Drawer.Body>

            {item ? (
              <Drawer.Footer className="p-0">
                <p className="m-0 hidden rounded-xl border border-border bg-surface-2 px-3.5 py-2.5 text-xs text-text-2 max-[767px]:block">
                  请使用桌面端领取会话。
                </p>
                <Button
                  variant="primary"
                  className="h-10 w-full max-[767px]:hidden"
                  onClick={onClaim}
                  disabled={disabled || claiming}
                >
                  {claiming ? "领取中…" : "领取会话"}
                </Button>
              </Drawer.Footer>
            ) : null}
          </Drawer.Dialog>
        </Drawer.Content>
      </Drawer.Backdrop>
    </Drawer>
  );
}
