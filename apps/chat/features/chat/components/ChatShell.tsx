"use client";

import type { Conversation, Customer } from "@/lib/session";

import { useChatMessages } from "../hooks/useChatMessages";

import { ChatBrand } from "./ChatBrand";
import { ChatComposer } from "./ChatComposer";
import { MessageList } from "./MessageList";

const QUEUE_NOTICE = "排队中，请稍候";

type ChatShellProps = {
  customer: Customer;
  conversation: Conversation | null;
  conversationNotFound?: boolean;
  error?: string | null;
  busy?: boolean;
  onLogout: () => void;
  onRetry?: () => void;
  onBack?: () => void;
};

const CHIP_BASE =
  "inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium";
const DOT_BASE = "h-1.5 w-1.5 rounded-full";

function statusMeta(status: string): { label: string; chip: string; dot: string } {
  switch (status) {
    case "QUEUED":
    case "CLAIMED":
      return {
        label: "人工接入中",
        chip: "border-warning-line bg-warning-soft text-warning",
        dot: "bg-warning",
      };
    case "HUMAN_ACTIVE":
      return {
        label: "人工服务中",
        chip: "border-accent-line bg-accent-soft text-accent-ink",
        dot: "bg-success",
      };
    case "CLOSED":
      return {
        label: "已结束",
        chip: "border-border bg-surface text-text-2",
        dot: "bg-text-3",
      };
    case "AI_ACTIVE":
      return {
        label: "AI 服务中",
        chip: "border-accent-line bg-accent-soft text-accent-ink",
        dot: "bg-success",
      };
    default:
      return {
        label: status,
        chip: "border-border bg-surface text-text-2",
        dot: "bg-text-3",
      };
  }
}

export function ChatShell({
  customer,
  conversation,
  conversationNotFound = false,
  error = null,
  busy = false,
  onLogout,
  onRetry,
  onBack,
}: ChatShellProps) {
  const {
    messages,
    status,
    loading,
    sending,
    messageError,
    draft,
    setDraft,
    trimmedLength,
    maxLength,
    overLimit,
    canSend,
    submitMessage,
  } = useChatMessages(conversation);

  const meta = statusMeta(status);
  // “排队中，请稍候”由等待卡/状态条承载；领取后改由“正在接入人工”说明，
  // 避免同一条提示在状态变化后重复出现在消息流里。
  const visibleMessages = messages.filter(
    (message) => !(message.author_type === "system" && message.content.trim() === QUEUE_NOTICE),
  );

  return (
    <main className="flex min-h-screen bg-canvas-deep p-10 max-[1024px]:p-0">
      <div className="flex flex-1 overflow-hidden rounded-[28px] bg-paper shadow-panel max-[1024px]:flex-col max-[1024px]:rounded-none">
        <ChatBrand customerName={customer.display_name} busy={busy} onLogout={onLogout} />

        <section className="flex min-w-0 flex-1 flex-col bg-paper">
          <header className="flex h-[76px] shrink-0 items-center gap-3 border-b border-border px-8 max-[1024px]:h-16 max-[1024px]:px-4">
            <div>
              <p className="m-0 text-xs font-semibold tracking-[0.2em] text-text-3">
                ONLINE SUPPORT
              </p>
              <h1 className="mt-1 text-lg font-semibold">在线支持</h1>
            </div>
            <span className={`${CHIP_BASE} ${meta.chip}`}>
              <span aria-hidden="true" className={`${DOT_BASE} ${meta.dot}`} />
              {meta.label}
            </span>
          </header>

          {error ? (
            <div
              className="mx-8 mt-3.5 flex items-center gap-2.5 rounded-md bg-danger-soft px-3.5 py-2.5 text-sm text-danger max-[1024px]:mx-4"
              role="alert"
            >
              <p className="m-0 flex-1">{error}</p>
              {onRetry ? (
                <button
                  className="rounded-md border border-current px-2.5 py-1 text-xs text-danger focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50"
                  type="button"
                  onClick={onRetry}
                  disabled={busy}
                >
                  重试
                </button>
              ) : null}
            </div>
          ) : null}

          {conversationNotFound ? (
            <div className="grid flex-1 place-items-center p-8">
              <div className="max-w-[360px] rounded-xl border border-border bg-surface p-6 text-center">
                <h2 className="mb-2 text-lg">会话不存在</h2>
                <p className="mb-4 text-sm leading-[1.7] text-text-2">
                  该会话不存在，或当前账号无权访问。
                </p>
                {onBack ? (
                  <button
                    className="rounded-md border border-border px-3.5 py-1.5 text-sm text-text focus-visible:outline-none focus-visible:shadow-focus"
                    type="button"
                    onClick={onBack}
                  >
                    返回
                  </button>
                ) : null}
              </div>
            </div>
          ) : conversation ? (
            <>
              {messageError ? (
                <p
                  className="mx-8 mt-3.5 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning max-[1024px]:mx-4"
                  role="alert"
                >
                  {messageError}
                </p>
              ) : null}
              <MessageList
                messages={visibleMessages}
                loading={loading}
                status={status}
                onQuick={(text) => void submitMessage(text)}
              />
              <div className="shrink-0 px-8 pb-6 pt-3.5 max-[1024px]:px-4 max-[1024px]:pb-4">
                <ChatComposer
                  draft={draft}
                  setDraft={setDraft}
                  sending={sending}
                  overLimit={overLimit}
                  trimmedLength={trimmedLength}
                  maxLength={maxLength}
                  canSend={canSend}
                  onSubmit={() => void submitMessage()}
                />
              </div>
            </>
          ) : null}
        </section>
      </div>
    </main>
  );
}
