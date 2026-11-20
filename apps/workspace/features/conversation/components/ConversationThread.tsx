"use client";

import type { ConversationDetail, MessagePage } from "../types";

import { useConversationMessages } from "../hooks/useConversationMessages";

import { ConversationMessageList } from "./ConversationMessageList";
import { ConversationReplyBox } from "./ConversationReplyBox";

type ConversationThreadProps = {
  conversationId: string;
  status: ConversationDetail["status"];
  /** 只有领取/人工中才轮询；转回 AI 后归属已清除，继续轮询只会 404。 */
  live: boolean;
  onStatus?: (status: MessagePage["status"]) => void;
};

const STATUS_HINT: Record<string, string> = {
  CLAIMED: "接管后可以回复客户。",
  CLOSED: "会话已结束，仅可查看。",
  AI_ACTIVE: "会话由 AI 接待，转人工并接管后可回复。",
  QUEUED: "客户正在排队，领取并接管后可回复。",
};

/** 会话页实时消息区：3s 轮询 + 接管后回复；回复框只在 HUMAN_ACTIVE 出现。 */
export function ConversationThread({
  conversationId,
  status,
  live,
  onStatus,
}: ConversationThreadProps) {
  const { messages, loading, sending, error, draft, setDraft, maxLength, submitReply } =
    useConversationMessages(conversationId, onStatus, live);

  return (
    <article className="rounded-2xl border border-border bg-surface px-6 py-5 shadow-panel max-[767px]:px-4">
      <div className="flex items-center gap-2">
        <h3 className="m-0 text-xs font-medium text-text-3">实时消息</h3>
        {live ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-text-3">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-online" />
            自动刷新
          </span>
        ) : null}
      </div>
      <div className="mt-3 flex flex-col gap-3">
        <ConversationMessageList messages={messages} loading={loading} />
        {error ? (
          <p
            className="m-0 rounded-xl border border-danger/15 bg-danger-soft px-3 py-2 text-sm text-danger"
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
