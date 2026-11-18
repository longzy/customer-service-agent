"use client";

import type { KeyboardEvent } from "react";

type ConversationReplyBoxProps = {
  draft: string;
  setDraft: (value: string) => void;
  sending: boolean;
  maxLength: number;
  onSubmit: () => void;
};

const KBD = "rounded-sm border border-border border-b-2 bg-bg px-1 text-xs text-text-2";

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
      className="rounded-[9px] border border-border bg-surface px-3 py-2 focus-within:border-accent focus-within:shadow-focus"
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
        className="block max-h-[120px] min-h-[26px] w-full resize-none border-0 bg-transparent p-0.5 text-sm leading-[1.65] text-text outline-none placeholder:text-text-3"
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
      <div className="mt-2 flex items-center gap-2">
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
          className="h-8 rounded-md border border-accent bg-accent px-3.5 text-sm font-medium text-surface hover:bg-brand-deep focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-2 disabled:text-text-3"
          type="submit"
          disabled={!canSend}
        >
          {sending ? "发送中…" : "发送"}
        </button>
      </div>
    </form>
  );
}
