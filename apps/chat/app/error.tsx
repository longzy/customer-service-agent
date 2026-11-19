"use client";

type ChatErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ChatError({ reset }: ChatErrorProps) {
  return (
    <main className="grid min-h-screen place-items-center bg-bg p-10 font-sans">
      <div className="w-full max-w-[420px] rounded-xl border border-border bg-surface p-6 text-center shadow-panel">
        <p className="m-0 text-sm leading-[1.7] text-text-2" role="alert">
          页面暂时无法加载，请稍后重试。
        </p>
        <button
          className="mt-4 h-9 rounded-md border border-border bg-surface px-3.5 text-sm text-text hover:border-border-strong focus-visible:outline-none focus-visible:shadow-focus"
          type="button"
          onClick={reset}
        >
          重试
        </button>
      </div>
    </main>
  );
}
