import { Suspense } from "react";

import { ChatLoading, SessionGate } from "@/features/chat";

export default function ChatPage() {
  return (
    <Suspense fallback={<ChatLoading />}>
      <SessionGate />
    </Suspense>
  );
}
