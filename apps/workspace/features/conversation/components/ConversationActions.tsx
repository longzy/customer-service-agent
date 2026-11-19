"use client";

import type { ConversationActionKind } from "../hooks/useConversationActions";

export type ConversationActionsProps = {
  busy: ConversationActionKind | null;
  /** 只有人工中才能转回 AI；已领取未接管只提供关闭。 */
  showReturn: boolean;
  onClose: () => void;
  onReturnToAi: () => void;
};

const BASE =
  "inline-flex h-[34px] items-center rounded-md border bg-surface px-3 text-sm focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3";

/** 已领取/人工中会话的出口：关闭是终态；只有人工中可转回 AI。已结束不渲染。 */
export function ConversationActions({
  busy,
  showReturn,
  onClose,
  onReturnToAi,
}: ConversationActionsProps) {
  return (
    <span className="flex items-center gap-2">
      {showReturn ? (
        <button
          className={`${BASE} border-border text-text hover:border-border-strong`}
          type="button"
          onClick={onReturnToAi}
          disabled={busy !== null}
        >
          {busy === "return" ? "转回中…" : "转回 AI"}
        </button>
      ) : null}
      <button
        className={`${BASE} border-border text-danger hover:border-danger`}
        type="button"
        onClick={onClose}
        disabled={busy !== null}
      >
        {busy === "close" ? "关闭中…" : "关闭会话"}
      </button>
    </span>
  );
}
