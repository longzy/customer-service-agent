import { Suspense } from "react";

import { SessionGate } from "@/components/SessionGate";

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <main className="app" aria-busy="true">
          <p className="loading">加载中…</p>
        </main>
      }
    >
      <SessionGate />
    </Suspense>
  );
}
