"use client";

import { useEffect, useId, useRef } from "react";

import { Button } from "@/components/ui/Button";
import { formatAmount, formatDateTime } from "@/lib/format";

import type { CancelDialogState } from "../hooks/useCancellation";
import type { CancellationTask, CustomerOrderSummary } from "../types";

// 影响说明是产品承诺，不随订单变化；文案只在这里出现一次。
const IMPACT_TEXT =
  "提交后订单进入取消受理。M1 只处理取消，不产生退款；已受理不等于已取消，最终状态以订单系统为准。";
const RESULT_TITLE = "取消结果";
const ERROR_TITLE = "操作失败";
const REFRESH_STATES = new Set(["SUBMITTING", "SUBMIT_UNKNOWN", "ACCEPTED"]);

type CancelDialogProps = {
  state: CancelDialogState;
  onConfirm: () => void;
  onDecline: () => void;
  onRefresh: () => void;
  onClose: () => void;
};

function OrderFacts({ order }: { order: CustomerOrderSummary }) {
  return (
    <dl className="m-0 grid grid-cols-2 gap-3 rounded-xl border border-border bg-surface-2 px-4 py-3 text-sm">
      <div className="col-span-2">
        <dt className="text-xs text-text-3">订单号</dt>
        <dd className="m-0 mt-0.5 select-all font-mono text-xs font-medium text-text">
          {order.order_id}
        </dd>
      </div>
      <div className="col-span-2">
        <dt className="text-xs text-text-3">商品</dt>
        <dd className="m-0 mt-0.5 font-medium text-text">{order.item_summary}</dd>
      </div>
      <div>
        <dt className="text-xs text-text-3">金额</dt>
        <dd className="m-0 mt-0.5 font-medium tabular-nums text-text">
          {formatAmount(order.amount_cents, order.currency)}
        </dd>
      </div>
      <div>
        <dt className="text-xs text-text-3">当前状态</dt>
        <dd className="m-0 mt-0.5 text-text">{order.status_label}</dd>
      </div>
    </dl>
  );
}

function ResultBody({ task }: { task: CancellationTask }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="m-0 text-base font-semibold text-text">{task.status_text}</p>
      {task.reason_text ? <p className="m-0 text-sm text-text-2">{task.reason_text}</p> : null}
      <p className="m-0 text-sm leading-relaxed text-text-2">{task.reply}</p>
    </div>
  );
}

export function CancelDialog({
  state,
  onConfirm,
  onDecline,
  onRefresh,
  onClose,
}: CancelDialogProps) {
  const titleId = useId();
  const primaryRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const isOpen = state.kind !== "closed";

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    previousFocus.current = document.activeElement as HTMLElement | null;
    return () => previousFocus.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    (primaryRef.current ?? panelRef.current)?.focus();
    const onKey = (event: KeyboardEvent) => {
      // 提交中按 Esc 不能关闭：关闭后再打开会回到旧结果，状态已变化。
      if (event.key === "Escape" && state.kind !== "submitting") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, onClose, state.kind]);

  if (state.kind === "closed") {
    return null;
  }

  const title =
    state.kind === "result" ? RESULT_TITLE : state.kind === "error" ? ERROR_TITLE : "确认取消订单";

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-brand-deep/50 px-4">
      <div
        aria-labelledby={titleId}
        aria-modal="true"
        className="w-full max-w-[420px] rounded-2xl border border-border bg-surface p-6 shadow-panel focus:outline-none"
        ref={panelRef}
        role="dialog"
        tabIndex={-1}
      >
        <h2 className="m-0 text-lg font-semibold tracking-[-0.01em]" id={titleId}>
          {title}
        </h2>

        {state.kind === "loading" ? (
          <div className="mt-4" role="status">
            <p className="m-0 text-sm text-text-2">正在准备确认信息…</p>
          </div>
        ) : null}

        {state.kind === "confirm" || state.kind === "submitting" ? (
          <div className="mt-4 flex flex-col gap-3">
            <OrderFacts order={state.order} />
            <p className="m-0 text-sm leading-relaxed text-text-2">{IMPACT_TEXT}</p>
            <p className="m-0 text-xs text-text-3">
              确认有效期至 {formatDateTime(state.task.expires_at)}
            </p>
            <p className="m-0 inline-flex w-fit items-center gap-1.5 rounded-full border border-warning-line bg-warning-soft px-2.5 py-1 text-xs text-warning-ink">
              尚未提交
            </p>
            <div className="mt-2 flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={state.kind === "submitting"}
                onClick={onDecline}
              >
                不取消
              </Button>
              <Button
                ref={primaryRef}
                variant="primary"
                size="sm"
                disabled={state.kind === "submitting"}
                onClick={onConfirm}
              >
                {state.kind === "submitting" ? "提交中…" : "确认取消"}
              </Button>
            </div>
          </div>
        ) : null}

        {state.kind === "result" ? (
          <div className="mt-4 flex flex-col gap-4">
            <ResultBody task={state.task} />
            <div className="flex justify-end gap-2">
              {REFRESH_STATES.has(state.task.state) ? (
                <Button variant="secondary" size="sm" onClick={onRefresh}>
                  刷新结果
                </Button>
              ) : null}
              <Button ref={primaryRef} variant="primary" size="sm" onClick={onClose}>
                关闭
              </Button>
            </div>
          </div>
        ) : null}

        {state.kind === "error" ? (
          <div className="mt-4 flex flex-col gap-4">
            <p className="m-0 text-sm leading-relaxed text-text-2" role="alert">
              {state.message}
            </p>
            <div className="flex justify-end">
              <Button ref={primaryRef} variant="primary" size="sm" onClick={onClose}>
                关闭
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
