import type { ConversationDetail, MessagePage } from "./types";

/**
 * 会话页状态合并：关闭/转回是终态，动作成功后晚到的轮询响应不得把状态覆盖回去；
 * 其余状态（如 CLAIMED → HUMAN_ACTIVE）以最新响应为准。
 * 关闭/转回同事务终态化交接单，本地同步交接单快照，避免“待办”仍显示为当前任务。
 */
export function mergeConversationStatus(
  current: ConversationDetail | null,
  status: MessagePage["status"],
): ConversationDetail | null {
  if (current === null) return current;
  if (current.status === "CLOSED" || current.status === "AI_ACTIVE") return current;
  const next = current.status === status ? current : { ...current, status };
  if (status !== "CLOSED" && status !== "AI_ACTIVE") return next;
  if (next.handoff === null) return next;
  return { ...next, handoff: { ...next.handoff, status: "CLOSED" } };
}
