import type { CancellationSummary } from "./types";

/**
 * 已提交但未收敛的任务：提交中、结果未知、已受理都要能继续刷新到最终结果。
 * 已受理不是永久终态（AC-67），列表项与结果卡共用这一口径。
 */
export const REFRESHABLE_CANCELLATION_STATES: ReadonlySet<string> = new Set([
  "SUBMITTING",
  "SUBMIT_UNKNOWN",
  "ACCEPTED",
]);

type RefreshableTask = Pick<CancellationSummary, "id" | "state">;

/** 有任务 id 且状态未收敛时才提供刷新入口；旧消息载荷无 id 时不显示。 */
export function canRefreshCancellation(cancellation: RefreshableTask): boolean {
  return Boolean(cancellation.id) && REFRESHABLE_CANCELLATION_STATES.has(cancellation.state);
}
