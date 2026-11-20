"use client";

import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/Button";

type WorkspaceHeaderProps = {
  total: number;
  overdue: number;
  loading: boolean;
  onRefresh: () => void;
};

export function WorkspaceHeader({ total, overdue, loading, onRefresh }: WorkspaceHeaderProps) {
  return (
    <div className="flex shrink-0 items-center gap-3 pt-5 max-[767px]:gap-2">
      <h1 className="m-0 text-xl font-semibold tracking-[-0.01em]">待接入队列</h1>
      <p className="m-0 text-xs text-text-3 max-[767px]:hidden">
        {total} 个等待 · {overdue} 个超时
      </p>
      <Button
        variant="secondary"
        size="sm"
        className="ml-auto shrink-0"
        onClick={onRefresh}
        disabled={loading}
      >
        <RefreshCw
          size={14}
          strokeWidth={1.8}
          aria-hidden="true"
          className={loading ? "animate-spin motion-reduce:animate-none" : ""}
        />
        刷新
      </Button>
    </div>
  );
}
