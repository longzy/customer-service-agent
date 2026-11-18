"use client";

import type { QueueItem } from "../types";

import { QueueEmpty, QueueError, QueueSkeleton } from "./QueueStates";
import { QueueTable } from "./QueueTable";

type QueueBodyProps = {
  items: QueueItem[] | null;
  visible: QueueItem[];
  total: number;
  loading: boolean;
  error: string | null;
  notice: string | null;
  selectedId: string | null;
  claimingId: string | null;
  disabled: boolean;
  onRetry: () => void;
  onRefresh: () => void;
  onClearFilters: () => void;
  onSelect: (id: string) => void;
  onClaim: (item: QueueItem) => void;
};

export function QueueBody({
  items,
  visible,
  total,
  loading,
  error,
  notice,
  selectedId,
  claimingId,
  disabled,
  onRetry,
  onRefresh,
  onClearFilters,
  onSelect,
  onClaim,
}: QueueBodyProps) {
  return (
    <>
      {notice ? (
        <p className="mt-3 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning" role="status">
          {notice}
        </p>
      ) : null}

      {error ? (
        <QueueError message={error} onRetry={onRetry} retrying={loading} />
      ) : loading && items === null ? (
        <QueueSkeleton />
      ) : items && items.length === 0 ? (
        <QueueEmpty onRefresh={onRefresh} />
      ) : visible.length === 0 ? (
        <div className="mt-3.5 flex min-h-[320px] flex-col items-center justify-center gap-2.5 rounded-xl border border-border bg-surface text-sm text-text-2">
          没有符合筛选条件的会话。
          <button
            className="h-8 rounded-md border border-border bg-surface px-3 text-sm text-text focus-visible:outline-none focus-visible:shadow-focus"
            type="button"
            onClick={onClearFilters}
          >
            清除筛选
          </button>
        </div>
      ) : (
        <QueueTable
          items={visible}
          total={total}
          selectedId={selectedId}
          claimingId={claimingId}
          disabled={disabled}
          onSelect={onSelect}
          onClaim={onClaim}
        />
      )}
    </>
  );
}
