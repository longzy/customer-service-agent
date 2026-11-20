"use client";

import type { KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";

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

const KBD =
  "rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] font-medium text-text-3";

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
      className="rounded-2xl border border-border bg-surface p-3 shadow-float transition-shadow focus-within:border-accent focus-within:shadow-focus"
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
        className="block max-h-[140px] min-h-[28px] w-full resize-none border-0 bg-transparent px-1 py-0.5 text-base leading-[1.65] text-text outline-none placeholder:text-text-3"
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
      <div className="mt-2.5 flex items-center gap-2.5 px-1">
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
          className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent text-white transition-colors hover:bg-accent/90 focus-visible:outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-text-3"
          type="submit"
          disabled={!canSend}
          aria-label={sending ? "发送中" : "发送"}
        >
          {sending ? (
            <span className="text-[11px]">…</span>
          ) : (
            <ArrowUp size={17} strokeWidth={2} aria-hidden="true" />
          )}
        </button>
      </div>
    </form>
  );
}
