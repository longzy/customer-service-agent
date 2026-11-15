"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ChatShell } from "@/components/ChatShell";
import { getSession, logout, type Account } from "@/lib/session";

export function SessionGate() {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    void getSession()
      .then((session) => {
        if (!session) {
          router.replace("/login");
          return;
        }
        setAccount(session);
        setReady(true);
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  if (!ready || !account) {
    return <main className="app" aria-busy="true" />;
  }

  return <ChatShell account={account} onLogout={() => void handleLogout()} />;
}
