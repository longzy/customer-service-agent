"use client";

import { useState } from "react";

const MAX_LENGTH = 500;

/**
 * M1 页面骨架：只实现空态与输入区。
 * 消息流、确认卡片与状态切换由 T-10 实现，规则见 ui.md。
 */
export function ChatShell() {
  const [value, setValue] = useState("");

  return (
    <main className="app">
      <header className="topbar">
        <span className="dot" aria-hidden="true" />
        <h1>客服中心</h1>
        <button type="button" className="ghost">
          转人工
        </button>
      </header>

      <div className="log">
        <p className="msg">您好，我可以帮您查询订单，或取消未发货的订单。</p>
        <div className="hints">
          <button type="button" className="hint">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.2-3.2" />
            </svg>
            查询订单
          </button>
          <button type="button" className="hint">
            <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <path d="M3.3 7 12 12l8.7-5" />
              <path d="M12 22V12" />
            </svg>
            取消订单
          </button>
        </div>
      </div>

      <div className="composer">
        <label className="sr-only" htmlFor="message">
          输入消息
        </label>
        <textarea
          id="message"
          className="cin"
          placeholder="输入消息，例如：取消订单 ORD-10001"
          rows={2}
          maxLength={MAX_LENGTH}
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <div className="cbar">
          <span className="hint-text">Enter 发送</span>
          <span className="count">
            {value.length}/{MAX_LENGTH}
          </span>
          <button type="button" className="send" aria-label="发送">
            发送
          </button>
        </div>
      </div>
    </main>
  );
}
