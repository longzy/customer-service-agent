"use client";

import type { ConversationDetail, MessagePage } from "../types";

import { useConversationMessages } from "../hooks/useConversationMessages";

import { ConversationMessageList } from "./ConversationMessageList";
import { ConversationReplyBox } from "./ConversationReplyBox";

type ConversationThreadProps = {
  conversationId: string;
  status: ConversationDetail["status"];
  onStatus?: (status: MessagePage["status"]) => void;
};

const STATUS_HINT: Record<string, string> = {
  CLAIMED: "接管后可以回复客户。",
  CLOSED: "会话已结束，仅可查看。",
  AI_ACTIVE: "会话由 AI 接待，转人工并接管后可回复。",
  QUEUED: "客户正在排队，领取并接管后可回复。",
};

/** 会话页实时消息区：3s 轮询 + 接管后回复；回复框只在 HUMAN_ACTIVE 出现。 */
export function ConversationThread({ conversationId, status, onStatus }: ConversationThreadProps) {
  const { messages, loading, sending, error, draft, setDraft, maxLength, submitReply } =
    useConversationMessages(conversationId, onStatus);

  return (
    <article className="rounded-xl border border-border bg-surface px-4 py-4">
      <h3 className="m-0 text-xs font-semibold tracking-[0.06em] text-text-2">实时消息</h3>
      <div className="mt-3 flex flex-col gap-2">
        <ConversationMessageList messages={messages} loading={loading} />
        {error ? (
          <p
            className="m-0 rounded-md bg-danger-soft px-2.5 py-1.5 text-sm text-danger"
            role="alert"
          >
            {error}
          </p>
        ) : null}
        {status === "HUMAN_ACTIVE" ? (
          <ConversationReplyBox
            draft={draft}
            setDraft={setDraft}
            sending={sending}
            maxLength={maxLength}
            onSubmit={() => void submitReply()}
          />
        ) : (
          <p className="m-0 text-sm text-text-3">{STATUS_HINT[status] ?? "当前状态不可回复。"}</p>
        )}
      </div>
    </article>
  );
}
