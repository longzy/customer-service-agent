"use client";

type ChatErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ChatError({ reset }: ChatErrorProps) {
  return (
    <main className="app">
      <section className="content">
        <div className="error-box">
          <p role="alert">页面暂时无法加载，请稍后重试。</p>
          <button type="button" className="ghost" onClick={reset}>
            重试
          </button>
        </div>
      </section>
    </main>
  );
}
