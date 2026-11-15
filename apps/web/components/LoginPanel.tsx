"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getAccounts, login, type Account } from "@/lib/session";

export function LoginPanel() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    void getAccounts()
      .then((items) => {
        setAccounts(items);
        setSelected(items[0]?.account_id ?? null);
        setLoaded(true);
      })
      .catch((cause: Error) => setError(cause.message));
  }, []);

  const current = accounts.find((account) => account.account_id === selected);

  async function handleEnter() {
    if (!current) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(current.account_id);
      router.push("/");
    } catch (cause) {
      setError((cause as Error).message);
      setBusy(false);
    }
  }

  return (
    <main className="login-wrap">
      <div className="login-card">
        <h1>客服中心</h1>
        <p className="login-note">开发期测试账号，请选择一个身份进入</p>
        {error ? (
          <p className="login-error" role="alert">
            {error}
          </p>
        ) : null}
        {loaded && accounts.length === 0 ? <p className="login-note">无可用账号</p> : null}
        <div className="account-list">
          {accounts.map((account) => (
            <button
              key={account.account_id}
              type="button"
              className={`account${account.account_id === selected ? " selected" : ""}`}
              aria-pressed={account.account_id === selected}
              onClick={() => setSelected(account.account_id)}
            >
              <span>{account.display_name}</span>
              <span className="account-tenant">{account.tenant_name}</span>
            </button>
          ))}
        </div>
        <button
          type="button"
          className="enter"
          onClick={() => void handleEnter()}
          disabled={!current || busy}
        >
          {current ? `以${current.display_name}身份进入` : "进入"}
        </button>
      </div>
    </main>
  );
}
