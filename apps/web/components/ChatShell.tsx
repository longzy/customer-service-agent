"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ConfirmCard, type Cancellation } from "@/components/ConfirmCard";
import { QueryView, type Order } from "@/components/QueryView";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  orders?: Order[];
  clarification?: string[];
  cancellation?: Cancellation;
};

type RetryAction =
  | { kind: "message"; content: string }
  | { kind: "act"; taskId: string; action: "confirm" | "abandon" };

type Reply = {
  conversation_id: string;
  reply: string;
  orders?: Order[];
  clarification?: string[];
  cancellation?: Cancellation;
};

const MAX_LENGTH = 500;

/**
 * M1 页面骨架：空态、消息列表、订单卡片与查询输入。
 * 流式输出、历史恢复与取消确认分别由后续任务实现。
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
  const [error, setError] = useState<{ message: string; retry: RetryAction } | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);

  function updateCard(
    taskId: string,
    body: { state: string; state_text: string; reason_code: string | null },
  ) {
    setMessages((items) =>
      items.map((item) =>
        item.cancellation?.task_id === taskId
          ? {
              ...item,
              cancellation: {
                ...item.cancellation,
                state: body.state,
                state_text: body.state_text,
                reason_code: body.reason_code,
              },
            }
          : item,
      ),
    );
  }

  async function act(taskId: string, action: "confirm" | "abandon") {
    setBusy(true);
    setError(null);
    const retry: RetryAction = { kind: "act", taskId, action };
    try {
      const response = await fetch(`/api/cancellation-requests/${taskId}/${action}`, {
        method: "POST",
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (response.status === 409) {
        const current = await fetch(`/api/cancellation-requests/${taskId}`);
        if (current.ok) {
          updateCard(taskId, await current.json());
          return;
        }
        setError({ message: "任务状态已变化，请稍后再试。", retry });
        return;
      }
      if (!response.ok) {
        setError({ message: "请求未完成，请重试。", retry });
        return;
      }
      updateCard(taskId, await response.json());
    } catch {
      setError({ message: "请求未完成，请重试。", retry });
    } finally {
      setBusy(false);
    }
  }

  async function submit(content: string, appendUser: boolean) {
    const text = content.trim();
    if (!text || busy) {
      return;
    }
    if (appendUser) {
      setMessages((items) => [...items, { id: `${Date.now()}-user`, role: "user", text }]);
    }
    setValue("");
    setError(null);
    setBusy(true);
    try {
      const response = await fetch("/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text, conversation_id: conversationId }),
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        setError({ message: "请求未完成，请重试。", retry: { kind: "message", content: text } });
        return;
      }
      const body = (await response.json()) as Reply;
      setConversationId(body.conversation_id);
      setMessages((items) => [
        ...items,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          text: body.reply,
          orders: body.orders,
          clarification: body.clarification,
          cancellation: body.cancellation,
        },
      ]);
    } catch {
      setError({ message: "请求未完成，请重试。", retry: { kind: "message", content: text } });
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

      <div className="log" role="log" aria-live="polite" aria-busy={busy}>
        {messages.length === 0 ? (
          <>
            <p className="msg">您好，我可以帮您查询订单，或取消未发货的订单。</p>
            <div className="hints">
              <button
                type="button"
                className="hint"
                onClick={() => void submit("查询我的最近订单", true)}
              >
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.2-3.2" />
                </svg>
                查询订单
              </button>
              <button
                type="button"
                className="hint"
                onClick={() => void submit("我要取消订单", true)}
              >
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                  <path d="M3.3 7 12 12l8.7-5" />
                  <path d="M12 22V12" />
                </svg>
                取消订单
              </button>
            </div>
          </>
        ) : null}
        {messages.map((message) => (
          <div key={message.id} className={`bubble ${message.role}`}>
            <p>{message.text}</p>
            {message.orders?.length ? <QueryView orders={message.orders} /> : null}
            {message.cancellation ? (
              <ConfirmCard
                cancellation={message.cancellation}
                busy={busy}
                onConfirm={() => void act(message.cancellation!.task_id, "confirm")}
                onAbandon={() => void act(message.cancellation!.task_id, "abandon")}
              />
            ) : null}
            {message.clarification?.length ? (
              <p className="hint-text">候选：{message.clarification.join("、")}</p>
            ) : null}
          </div>
        ))}
        {busy ? (
          <p className="msg" role="status">
            正在查询…
          </p>
        ) : null}
        {error ? (
          <div className="bubble assistant">
            <p role="alert">{error.message}</p>
            <button
              type="button"
              className="ghost"
              onClick={() =>
                error.retry.kind === "message"
                  ? void submit(error.retry.content, false)
                  : void act(error.retry.taskId, error.retry.action)
              }
            >
              重试
            </button>
          </div>
        ) : null}
      </div>

      <div className="composer" aria-busy={busy}>
        <label className="sr-only" htmlFor="message">
          输入消息
        </label>
        <textarea
          id="message"
          className="cin"
          placeholder="输入消息，例如：查询订单 ORD-10001"
          rows={2}
          maxLength={MAX_LENGTH}
          value={value}
          disabled={busy}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) {
              return;
            }
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit(value, true);
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
            onClick={() => void submit(value, true)}
            disabled={busy || value.trim().length === 0}
          >
            发送
          </button>
        </div>
      </div>
    </main>
  );
}
