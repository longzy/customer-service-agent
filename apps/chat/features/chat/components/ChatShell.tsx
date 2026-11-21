"use client";

import { useRouter } from "next/navigation";

import type { Conversation, Customer } from "@/lib/session";

import { useChatMessages } from "../hooks/useChatMessages";

import { ChatComposer } from "./ChatComposer";
import { ChatHeader } from "./ChatHeader";
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

function statusMeta(status: string): { label: string; chip: string; dot: string } {
  switch (status) {
    case "QUEUED":
    case "CLAIMED":
      return {
        label: "人工接入中",
        chip: "border-warning-line bg-warning-soft text-warning-ink",
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
        chip: "border-border bg-surface-2 text-text-2",
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
        chip: "border-border bg-surface-2 text-text-2",
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
  const router = useRouter();
  const {
    messages,
    status,
    loading,
    sending,
    closing,
    messageError,
    draft,
    setDraft,
    trimmedLength,
    maxLength,
    overLimit,
    canSend,
    submitMessage,
    closeCurrentSession,
  } = useChatMessages(conversation);

  const meta = statusMeta(status);
  // “排队中，请稍候”由等待卡/状态条承载；领取后改由“正在接入人工”说明，
  // 避免同一条提示在状态变化后重复出现在消息流里。
  const visibleMessages = messages.filter(
    (message) => !(message.author_type === "system" && message.content.trim() === QUEUE_NOTICE),
  );

  return (
    <main className="flex h-dvh flex-col overflow-hidden bg-bg">
      <ChatHeader
        customerName={customer.display_name}
        statusLabel={meta.label}
        chipClass={meta.chip}
        dotClass={meta.dot}
        closed={status === "CLOSED"}
        closing={closing}
        busy={busy}
        onOpenOrders={() => router.push("/orders")}
        onClose={() => void closeCurrentSession()}
        onLogout={onLogout}
      />

      <div className="mx-auto flex min-h-0 w-full max-w-[860px] flex-1 flex-col px-6 max-[1023px]:px-4">
        {error ? (
          <div
            className="mt-4 flex items-center gap-2.5 rounded-xl border border-danger/15 bg-danger-soft px-3.5 py-2.5 text-sm text-danger"
            role="alert"
          >
            <p className="m-0 flex-1">{error}</p>
            {onRetry ? (
              <button
                className="rounded-md border border-current px-2.5 py-1 text-xs font-medium transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:shadow-focus disabled:opacity-50"
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
          <div className="grid flex-1 place-items-center py-12">
            <div className="w-full max-w-[380px] rounded-2xl border border-border bg-surface p-8 text-center shadow-panel">
              <h2 className="m-0 text-lg font-semibold">会话不存在</h2>
              <p className="mt-2 text-sm leading-relaxed text-text-2">
                该会话不存在，或当前账号无权访问。
              </p>
              {onBack ? (
                <button
                  className="mt-5 inline-flex h-9 items-center rounded-lg border border-border bg-surface px-4 text-sm text-text transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:shadow-focus"
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
                className="mt-4 m-0 rounded-xl border border-warning-line bg-warning-soft px-3.5 py-2.5 text-sm text-warning-ink"
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
            {status === "CLOSED" ? null : (
              <div className="shrink-0 pb-6 pt-4 max-[767px]:sticky max-[767px]:bottom-0 max-[767px]:bg-bg max-[767px]:pb-4">
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
                <p className="mt-3 text-center text-xs text-text-3">
                  对话由真人客服与 AI 助手共同提供 · 请勿发送支付密码等敏感信息
                </p>
              </div>
            )}
          </>
        ) : null}
      </div>
    </main>
  );
}
