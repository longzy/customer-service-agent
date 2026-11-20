"use client";

import type { KeyboardEvent } from "react";
type ConversationReplyBoxProps = {
  draft: string;
  setDraft: (value: string) => void;
  sending: boolean;
  maxLength: number;
  onSubmit: () => void;
};

const KBD =
  "rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] font-medium text-text-3";

/** 坐席回复输入：Enter 发送、Shift+Enter 换行；输入法合成中的 Enter 不发送。 */
export function ConversationReplyBox({
  draft,
  setDraft,
  sending,
  maxLength,
  onSubmit,
}: ConversationReplyBoxProps) {
  const trimmedLength = draft.trim().length;
  const overLimit = trimmedLength > maxLength;
  const canSend = !sending && trimmedLength > 0 && !overLimit;

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) {
        onSubmit();
      }
    }
  }

  return (
    <form
      className="rounded-xl border border-border bg-surface px-3 py-2.5 transition-shadow focus-within:border-accent focus-within:shadow-focus"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) {
          onSubmit();
        }
      }}
    >
      <label className="sr-only" htmlFor="reply-input">
        回复客户
      </label>
      <textarea
        className="block max-h-[140px] min-h-[28px] w-full resize-none border-0 bg-transparent px-1 py-0.5 text-sm leading-relaxed text-text outline-none placeholder:text-text-3"
        id="reply-input"
        name="content"
        rows={2}
        placeholder="回复客户…"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        aria-invalid={overLimit}
        aria-describedby="reply-hint"
      />
      <div className="mt-2 flex items-center gap-2 px-1">
        <span className="hidden text-xs text-text-3 min-[1025px]:inline">
          <kbd className={KBD}>Enter</kbd> 发送 · <kbd className={KBD}>Shift</kbd> +{" "}
          <kbd className={KBD}>Enter</kbd> 换行
        </span>
        <span
          id="reply-hint"
          className={`ml-auto text-xs tabular-nums ${overLimit ? "text-danger" : "text-text-3"}`}
          aria-live="polite"
        >
          {trimmedLength}/{maxLength}
        </span>
        <button
          className="grid h-8 place-items-center rounded-lg bg-accent px-3.5 text-sm font-medium text-white transition-colors hover:bg-accent/90 focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-text-3"
          type="submit"
          disabled={!canSend}
        >
          {sending ? "发送中…" : "发送"}
        </button>
      </div>
    </form>
  );
}
