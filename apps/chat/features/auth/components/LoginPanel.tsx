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

const INPUT_WRAP =
  "flex h-11 items-center gap-2 rounded-lg border border-input-border bg-surface px-3 transition-colors focus-within:border-accent focus-within:shadow-focus";

const INPUT =
  "min-w-0 flex-1 bg-transparent text-base text-text outline-none placeholder:text-text-3";

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
        router.replace("/chat");
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
      router.replace("/chat");
    } catch (cause) {
      const message = cause instanceof Error && cause.message ? cause.message : "登录失败，请重试";
      setError({ message, retryCheck: false });
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen bg-canvas-deep p-10 max-[1024px]:p-0">
      <div className="flex flex-1 overflow-hidden rounded-[28px] bg-bg shadow-panel max-[1024px]:flex-col max-[1024px]:rounded-none">
        <LoginBrand />

        <section className="relative flex flex-1 flex-col items-center justify-center gap-4 px-10 py-10 max-[1024px]:px-5 max-[1024px]:pb-10 max-[1024px]:pt-6">
          <p className="absolute right-10 top-8 text-xs tracking-[0.18em] text-text-3 max-[1024px]:hidden">
            SECURE SIGN IN
          </p>

          <form
            className="w-full max-w-[400px] rounded-[20px] border border-border bg-surface px-9 pb-7 pt-9 shadow-panel max-[1024px]:px-6"
            onSubmit={handleSubmit}
            aria-busy={busy}
          >
            <p className="text-xs font-semibold tracking-[0.2em] text-text-3">CUSTOMER CENTER</p>
            <h2 className="mt-2.5 font-serif text-[27px] font-semibold tracking-[0.01em]">
              登录客服中心
            </h2>
            <p className="mt-2 text-sm leading-[1.7] text-text-2">
              使用你的客户账号登录，继续之前的对话。
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
                  账号
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

              <p className="-mt-1 text-xs text-text-3">连续 5 次失败将锁定 15 分钟</p>

              <Button
                className="mt-0.5 w-full"
                size="lg"
                type="submit"
                disabled={checking || busy || !username.trim() || !password}
              >
                {busy ? "进入对话中…" : "进入对话"}
              </Button>
            </div>

            <div className="mt-5 flex items-center gap-2.5 text-xs text-text-3 before:h-px before:flex-1 before:bg-line-soft after:h-px after:flex-1 after:bg-line-soft">
              <span>账号由客服中心开通</span>
            </div>
            <p className="mt-3.5 text-center text-xs leading-[1.7] text-text-2">
              忘记密码？联系在线客服重置，无需注册。
            </p>

            {process.env.NODE_ENV !== "production" ? (
              <p className="mt-4 rounded-md border border-notice-line bg-notice-bg px-3 py-2.5 text-xs leading-[1.7] text-notice-ink">
                <b className="font-semibold text-notice-strong">开发期测试账号</b>：见项目 README，
                生产环境不展示此提示。
              </p>
            ) : null}
          </form>

          <p className="text-xs text-text-3">对话内容加密传输 · 仅用于本次服务</p>
        </section>
      </div>
    </main>
  );
}
