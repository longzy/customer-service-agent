"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Eye } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { getSession, login } from "@/lib/session";

import { LoginBrand } from "./LoginBrand";

type LoginError = {
  message: string;
  retryCheck: boolean;
};

const EYE_ICON = <Eye size={16} strokeWidth={1.6} aria-hidden="true" />;

const FIELD = "flex flex-col gap-2";

const FIELD_LABEL = "text-sm font-medium text-text-2";

const REVEAL =
  "absolute right-1.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-md text-text-3 transition-colors hover:bg-surface-2 hover:text-text-2 focus-visible:outline-none focus-visible:shadow-focus";

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
    <main className="flex min-h-screen items-center justify-center bg-bg p-8 max-[1023px]:p-0">
      <div className="grid w-full max-w-[1040px] overflow-hidden rounded-3xl border border-border bg-surface shadow-panel min-[1024px]:min-h-[620px] min-[1024px]:grid-cols-[0.9fr_1fr] max-[1023px]:min-h-screen max-[1023px]:max-w-none max-[1023px]:grid-cols-1 max-[1023px]:rounded-none max-[1023px]:border-0 max-[1023px]:shadow-none">
        <LoginBrand />

        <section className="flex flex-col px-10 py-12 max-[1023px]:px-6 max-[1023px]:py-8">
          <div className="mx-auto flex w-full max-w-[368px] flex-1 flex-col justify-center">
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-accent-ink">
              客户登录
            </p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.02em]">登录客服中心</h2>
            <p className="mt-2 text-sm leading-relaxed text-text-2">
              使用你的客户账号登录，继续之前的对话。
            </p>

            {error ? (
              <div
                className="mt-6 flex items-start gap-2.5 rounded-xl border border-danger/15 bg-danger-soft px-3.5 py-3 text-sm leading-relaxed text-danger"
                role="alert"
              >
                <p className="flex-1">{error.message}</p>
                {error.retryCheck ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    onClick={() => void checkSession()}
                    disabled={checking}
                  >
                    重试
                  </Button>
                ) : null}
              </div>
            ) : null}

            <form className="mt-7 flex flex-col gap-5" onSubmit={handleSubmit} aria-busy={busy}>
              <div className={FIELD}>
                <label className={FIELD_LABEL} htmlFor="username">
                  账号
                </label>
                <Input
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

              <div className={FIELD}>
                <label className={FIELD_LABEL} htmlFor="password">
                  密码
                </label>
                <div className="relative">
                  <Input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    className="pr-11"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    className={REVEAL}
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
                className="w-full"
                size="lg"
                type="submit"
                disabled={checking || busy || !username.trim() || !password}
              >
                {busy ? "进入对话中…" : "进入对话"}
              </Button>
            </form>

            <div className="mt-8 border-t border-line-soft pt-5">
              <p className="text-xs leading-relaxed text-text-3">
                账号由客服中心开通，忘记密码请联系在线客服重置，无需注册。
              </p>
            </div>

            {process.env.NODE_ENV !== "production" ? (
              <p className="mt-4 rounded-xl border border-notice-line bg-notice-bg px-3.5 py-2.5 text-xs leading-relaxed text-notice-ink">
                <b className="font-semibold text-notice-strong">开发期测试账号</b>：见项目 README，
                生产环境不展示此提示。
              </p>
            ) : null}

            <p className="mt-8 text-center text-xs text-text-3">
              对话内容加密传输 · 仅用于本次服务
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
