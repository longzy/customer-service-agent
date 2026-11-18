"use client";

import type { KeyboardEvent } from "react";

type ChatComposerProps = {
  draft: string;
  setDraft: (value: string) => void;
  sending: boolean;
  overLimit: boolean;
  trimmedLength: number;
  maxLength: number;
  canSend: boolean;
  onSubmit: () => void;
};

const KBD = "rounded-sm border border-border border-b-2 bg-bg px-1 text-xs text-text-2";

export function ChatComposer({
  draft,
  setDraft,
  sending,
  overLimit,
  trimmedLength,
  maxLength,
  canSend,
  onSubmit,
}: ChatComposerProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter 发送，Shift+Enter 换行；输入法合成中的 Enter 不发送。
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) {
        onSubmit();
      }
    }
  }

  return (
    <form
      className="rounded-xl border border-border bg-surface px-3.5 pb-2.5 pt-3 shadow-lift focus-within:border-accent focus-within:shadow-focus"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) {
          onSubmit();
        }
      }}
    >
      <label className="sr-only" htmlFor="message-input">
        消息
      </label>
      <textarea
        className="block max-h-[120px] min-h-[26px] w-full resize-none border-0 bg-transparent p-0.5 text-base leading-[1.65] text-text outline-none placeholder:text-text-3"
        id="message-input"
        name="content"
        rows={1}
        placeholder="输入消息…"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        aria-invalid={overLimit}
        aria-describedby="message-hint"
      />
      <div className="mt-2 flex items-center gap-2.5">
        <span className="hidden text-xs text-text-3 min-[1025px]:inline">
          <kbd className={KBD}>Enter</kbd> 发送 · <kbd className={KBD}>Shift</kbd> +{" "}
          <kbd className={KBD}>Enter</kbd> 换行
        </span>
        <span
          id="message-hint"
          className={`ml-auto text-xs tabular-nums ${overLimit ? "text-danger" : "text-text-3"}`}
          aria-live="polite"
        >
          {trimmedLength}/{maxLength}
        </span>
        <button
          className="grid h-[38px] w-[38px] shrink-0 place-items-center rounded-xl bg-accent text-surface hover:bg-brand-deep focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-text-3"
          type="submit"
          disabled={!canSend}
          aria-label={sending ? "发送中" : "发送"}
        >
          {sending ? (
            <span className="text-xs">发送中</span>
          ) : (
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
              <path
                d="M3 9h11M10 4.5L14.5 9 10 13.5"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
      </div>
    </form>
  );
}
