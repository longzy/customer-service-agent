"use client";

import styles from "./QueueKeyBar.module.css";

export function QueueKeyBar() {
  return (
    <div className={styles.keybar}>
      <span>
        <kbd>J</kbd>
        <kbd>K</kbd> 选择
      </span>
      <span>
        <kbd>Enter</kbd> 领取
      </span>
      <span>
        <kbd>⌘K</kbd> 搜索
      </span>
      <span>
        <kbd>?</kbd> 快捷键
      </span>
      <span className={styles.grow} />
      <span className={styles.conn}>
        <span className={styles.dot} aria-hidden="true" />
        已连接 · 自动刷新 30s
      </span>
    </div>
  );
}
