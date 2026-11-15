"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ChatShell } from "@/components/ChatShell";
import { getSession, logout, type Account } from "@/lib/session";

export function SessionGate() {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [error, setError] = useState<{ message: string; retry: "load" | "logout" } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const session = await getSession();
      if (!session) {
        router.replace("/login");
        return;
      }
      setAccount(session);
    } catch {
      setError({ message: "请求未完成，请重试", retry: "load" });
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleLogout() {
    try {
      await logout();
      router.replace("/login");
    } catch {
      setError({ message: "退出失败，请重试", retry: "logout" });
    }
  }

  if (error) {
    return (
      <main className="app">
        <p role="alert">{error.message}</p>
        <button
          type="button"
          className="ghost"
          onClick={() => void (error.retry === "logout" ? handleLogout() : load())}
        >
          重试
        </button>
      </main>
    );
  }

  if (!account) {
    return <main className="app" aria-busy="true" />;
  }

  return <ChatShell account={account} onLogout={() => void handleLogout()} />;
}
