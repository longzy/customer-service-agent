"use client";

import { Button } from "@/components/ui/Button";

import type { QueueItem } from "../types";

import { QueueEmpty, QueueError, QueueSkeleton } from "./QueueStates";
import { QueueTable } from "./QueueTable";

type QueueBodyProps = {
  items: QueueItem[] | null;
  visible: QueueItem[];
  total: number;
  page: number;
  pageCount: number;
  loading: boolean;
  error: string | null;
  errorCode?: string;
  notice: string | null;
  selectedId: string | null;
  claimingId: string | null;
  disabled: boolean;
  onPageChange: (page: number) => void;
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
  page,
  pageCount,
  loading,
  error,
  errorCode,
  notice,
  selectedId,
  claimingId,
  disabled,
  onPageChange,
  onRetry,
  onRefresh,
  onClearFilters,
  onSelect,
  onClaim,
}: QueueBodyProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 pt-4">
      {notice ? (
        <p
          className="m-0 rounded-xl border border-warning-line bg-warning-soft px-3.5 py-2.5 text-sm text-warning-ink"
          role="status"
        >
          {notice}
        </p>
      ) : null}

      {error ? (
        <QueueError message={error} code={errorCode} onRetry={onRetry} retrying={loading} />
      ) : loading && items === null ? (
        <QueueSkeleton />
      ) : items && items.length === 0 ? (
        <QueueEmpty onRefresh={onRefresh} />
      ) : visible.length === 0 ? (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-surface p-8 text-center text-sm text-text-2 shadow-panel">
          没有符合筛选条件的会话。
          <Button variant="secondary" size="sm" onClick={onClearFilters}>
            清除筛选
          </Button>
        </div>
      ) : (
        <QueueTable
          items={visible}
          total={total}
          page={page}
          pageCount={pageCount}
          onPageChange={onPageChange}
          selectedId={selectedId}
          claimingId={claimingId}
          disabled={disabled}
          onSelect={onSelect}
          onClaim={onClaim}
        />
      )}
    </div>
  );
}
