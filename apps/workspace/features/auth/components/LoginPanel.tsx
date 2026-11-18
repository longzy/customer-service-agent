"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { getSession, login } from "@/lib/session";

import styles from "./LoginPanel.module.css";
import { LoginBrand } from "./LoginBrand";

type LoginError = {
  message: string;
  retryCheck: boolean;
};

const EYE_ICON = (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M1.8 8S4 3.8 8 3.8 14.2 8 14.2 8 12 12.2 8 12.2 1.8 8 1.8 8Z"
      stroke="currentColor"
      strokeWidth="1.3"
    />
    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3" />
  </svg>
);

const SHIELD_ICON = (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path
      d="M8 1.8 13 3.6v4.1c0 3-2.1 5.4-5 6.5-2.9-1.1-5-3.5-5-6.5V3.6L8 1.8Z"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinejoin="round"
    />
  </svg>
);

const isDev = process.env.NODE_ENV !== "production";

export function LoginPanel() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<LoginError | null>(null);

  const checkSession = useCallback(async () => {
    setChecking(true);
    setError(null);
    try {
      const session = await getSession();
      if (session) {
        router.replace("/queue");
        return;
      }
    } catch {
      setError({ message: "无法确认登录状态，请重试", retryCheck: true });
    }
    setChecking(false);
  }, [router]);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (checking || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      router.replace("/queue");
    } catch (cause) {
      const message = cause instanceof Error && cause.message ? cause.message : "登录失败，请重试";
      setError({ message, retryCheck: false });
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <LoginBrand />

      <section className={styles.pane}>
        <p className={styles.help}>登录遇到问题？</p>

        <form className={styles.card} onSubmit={handleSubmit} aria-busy={busy}>
          <div className={styles.cardHead}>
            <p className={styles.kicker}>AGENT SIGN IN</p>
            {isDev ? <span className={styles.badge}>DEV</span> : null}
          </div>
          <h2 className={styles.title}>登录工作台</h2>
          <p className={styles.sub}>使用员工账号登录，进入待接入队列。</p>

          {error ? (
            <div className={styles.error} role="alert">
              <div className={styles.errorRow}>
                <p>{error.message}</p>
                {error.retryCheck ? (
                  <Button
                    variant="ghost"
                    type="button"
                    onClick={() => void checkSession()}
                    disabled={checking}
                  >
                    重试
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className={styles.form}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="username">
                工号或邮箱
              </label>
              <div className={styles.inputWrap}>
                <input
                  className={styles.input}
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                />
              </div>
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="password">
                密码
              </label>
              <div className={styles.inputWrap}>
                <input
                  className={styles.input}
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  className={styles.eye}
                  type="button"
                  aria-label={showPassword ? "隐藏密码" : "显示密码"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {EYE_ICON}
                </button>
              </div>
            </div>

            <label className={styles.keep}>
              <input className={styles.checkbox} type="checkbox" checked disabled />
              在此设备保持登录 8 小时（固定策略）
            </label>

            <Button
              className={styles.submit}
              size="lg"
              type="submit"
              disabled={checking || busy || !username.trim() || !password}
            >
              {busy ? "登录中…" : "登录"}
            </Button>
          </div>

          <div className={styles.audit}>
            {SHIELD_ICON}
            <span>仅限内部员工。登录、领取与关闭会话均记录在审计日志中，用于安全追溯。</span>
          </div>

          <p className={styles.last}>上次登录：11-17 18:20 · 上海</p>
        </form>
      </section>
    </main>
  );
}
