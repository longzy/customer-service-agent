"use client";

import type { KeyboardEvent } from "react";

import styles from "./ChatComposer.module.css";

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
      className={styles.composer}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) {
          onSubmit();
        }
      }}
    >
      <label className={styles.srOnly} htmlFor="message-input">
        消息
      </label>
      <textarea
        className={styles.input}
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
      <div className={styles.foot}>
        <span className={styles.hint}>
          <kbd>Enter</kbd> 发送 · <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行
        </span>
        <span
          id="message-hint"
          className={overLimit ? styles.countOver : styles.count}
          aria-live="polite"
        >
          {trimmedLength}/{maxLength}
        </span>
        <button className={styles.send} type="submit" disabled={!canSend} aria-label={sending ? "发送中" : "发送"}>
          {sending ? (
            <span className={styles.sending}>发送中</span>
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
