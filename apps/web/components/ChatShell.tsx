"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { QueryView, type Order } from "@/components/QueryView";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  orders?: Order[];
  clarification?: string[];
};

type Reply = {
  reply: string;
  orders?: Order[];
  clarification?: string[];
};

const MAX_LENGTH = 500;

/**
 * M1 页面骨架：只实现空态与输入区。
 * 消息流、确认卡片与状态切换由 T-10 实现，规则见 ui.md。
 */
export function ChatShell({
  account,
  onLogout,
}: {
  account?: { display_name: string; tenant_name: string };
  onLogout?: () => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    const content = value.trim();
    if (!content || busy) {
      return;
    }
    setValue("");
    setError(null);
    setBusy(true);
    setMessages((items) => [...items, { id: `${Date.now()}-user`, role: "user", text: content }]);
    try {
      const response = await fetch("/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        setError("服务暂时不可用，请稍后再试。");
        return;
      }
      const body = (await response.json()) as Reply;
      setMessages((items) => [
        ...items,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          text: body.reply,
          orders: body.orders,
          clarification: body.clarification,
        },
      ]);
    } catch {
      setError("网络异常，请稍后再试。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app">
      <header className="topbar">
        <span className="dot" aria-hidden="true" />
        <h1>客服中心</h1>
        {account ? (
          <span className="who">
            {account.tenant_name} · {account.display_name}
          </span>
        ) : null}
        <button type="button" className="ghost">
          转人工
        </button>
        {onLogout ? (
          <button type="button" className="ghost" onClick={onLogout}>
            退出
          </button>
        ) : null}
      </header>

      <div className="log">
        {messages.length === 0 ? (
          <p className="msg">您好，我可以帮您查询订单，或取消未发货的订单。</p>
        ) : null}
        {messages.length === 0 ? (
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
        ) : null}
        {messages.map((message) => (
          <div key={message.id} className={`bubble ${message.role}`}>
            <p>{message.text}</p>
            {message.orders?.length ? <QueryView orders={message.orders} /> : null}
            {message.clarification?.length ? (
              <p className="hint-text">候选：{message.clarification.join("、")}</p>
            ) : null}
          </div>
        ))}
        {busy ? <p className="msg">正在查询…</p> : null}
        {error ? (
          <p className="login-error" role="alert">
            {error}
          </p>
        ) : null}
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
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="cbar">
          <span className="hint-text">Enter 发送</span>
          <span className="count">
            {value.length}/{MAX_LENGTH}
          </span>
          <button
            type="button"
            className="send"
            aria-label="发送"
            onClick={() => void send()}
            disabled={busy}
          >
            发送
          </button>
        </div>
      </div>
    </main>
  );
}
