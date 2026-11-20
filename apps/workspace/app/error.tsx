"use client";

import { Button } from "@/components/ui/Button";

type WorkspaceErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function WorkspaceError({ reset }: WorkspaceErrorProps) {
  return (
    <main className="grid min-h-dvh place-items-center bg-bg p-8 font-sans">
      <div className="w-full max-w-[400px] rounded-2xl border border-border bg-surface p-8 text-center shadow-panel">
        <h1 className="m-0 text-lg font-semibold">页面暂时无法加载</h1>
        <p className="mt-2 text-sm leading-relaxed text-text-2" role="alert">
          请稍后重试；如果问题持续出现，请联系系统管理员。
        </p>
        <Button className="mt-5" onClick={reset}>
          重试
        </Button>
      </div>
    </main>
  );
}
