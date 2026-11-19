"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { getSession, login } from "@/lib/session";

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

const INPUT_WRAP =
  "flex h-[42px] items-center gap-2 rounded-md border border-input-border bg-surface px-3 transition-colors focus-within:border-accent focus-within:shadow-focus";

const INPUT =
  "min-w-0 flex-1 bg-transparent text-base text-text outline-none placeholder:text-text-3";

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
    <main className="flex min-h-screen bg-canvas-deep p-10 max-[1023px]:p-0">
      <div className="flex flex-1 overflow-hidden rounded-[28px] bg-bg shadow-panel max-[1023px]:flex-col max-[1023px]:rounded-none">
        <LoginBrand isDev={isDev} />

        <section className="relative flex flex-1 flex-col items-center justify-center gap-4 px-10 py-10 max-[1023px]:px-5 max-[1023px]:pb-10 max-[1023px]:pt-6">
          <p className="absolute right-10 top-8 text-xs text-text-2 max-[1023px]:hidden">
            内部支持请联系管理员
          </p>

          <form
            className="w-full max-w-[400px] rounded-[18px] border border-border bg-surface px-9 pb-7 pt-8 shadow-panel max-[1023px]:px-6"
            onSubmit={handleSubmit}
            aria-busy={busy}
          >
            <div className="flex items-center">
              <p className="m-0 text-xs font-semibold tracking-[0.18em] text-text-3">
                AGENT SIGN IN
              </p>
              <span className="ml-auto rounded-full border border-notice-line bg-notice-bg px-2 py-0.5 text-xs tracking-[0.08em] text-notice-ink">
                {isDev ? "DEV" : "PROD"}
              </span>
            </div>
            <h2 className="mt-2.5 text-[23px] font-semibold tracking-[-0.01em]">登录工作台</h2>
            <p className="mt-2 text-sm leading-[1.7] text-text-2">
              使用员工账号登录，进入待接入队列。
            </p>

            {error ? (
              <div
                className="mt-4 rounded-md bg-danger-soft px-3 py-2.5 text-sm leading-relaxed text-danger"
                role="alert"
              >
                <div className="flex items-center gap-2.5">
                  <p className="flex-1">{error.message}</p>
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

            <div className="mt-6 flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-text-2" htmlFor="username">
                  工号或邮箱
                </label>
                <div className={INPUT_WRAP}>
                  <input
                    className={INPUT}
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

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-text-2" htmlFor="password">
                  密码
                </label>
                <div className={INPUT_WRAP}>
                  <input
                    className={INPUT}
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    className="-m-1 grid place-items-center rounded-sm p-1 text-text-3 hover:text-text-2 focus-visible:outline-none focus-visible:shadow-focus"
                    type="button"
                    aria-label={showPassword ? "隐藏密码" : "显示密码"}
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword((value) => !value)}
                  >
                    {EYE_ICON}
                  </button>
                </div>
              </div>

              <label className="flex items-center gap-2 text-xs text-text-2">
                <input
                  className="h-[15px] w-[15px] shrink-0 appearance-none rounded-sm border border-border-strong bg-surface checked:border-accent checked:bg-accent disabled:opacity-75"
                  type="checkbox"
                  checked
                  disabled
                />
                在此设备保持登录 8 小时（固定策略）
              </label>

              <Button
                className="mt-1 w-full"
                size="lg"
                type="submit"
                disabled={checking || busy || !username.trim() || !password}
              >
                {busy ? "登录中…" : "登录"}
              </Button>
            </div>

            <div className="mt-5 flex gap-1.5 border-t border-line-soft pt-3.5 text-xs leading-[1.8] text-text-3">
              <span className="mt-0.5 shrink-0">{SHIELD_ICON}</span>
              <span>仅限内部员工。登录、领取与关闭会话均记录在审计日志中，用于安全追溯。</span>
            </div>
          </form>
        </section>
      </div>
    </main>
  );
}
