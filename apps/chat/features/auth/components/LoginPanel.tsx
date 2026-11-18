"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { getSession, login } from "@/lib/session";

import styles from "./LoginPanel.module.css";

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
    <main className={styles.page}>
      <aside className={styles.brand} aria-label="回声客服">
        <div className={styles.logo}>
          <span className={styles.logoMark}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path
                d="M4 6.5a7 7 0 0 1 12 0"
                stroke="#eaf4ef"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
              <path
                d="M6.2 9.5a4.6 4.6 0 0 1 7.6 0"
                stroke="#9ec7b8"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
              <circle cx="10" cy="12.6" r="1.5" fill="#eaf4ef" />
            </svg>
          </span>
          <span>
            <span className={styles.logoName}>回声 ECHO</span>
            <span className={styles.logoSub}>CUSTOMER CARE</span>
          </span>
        </div>

        <h1 className={styles.headline}>
          有问题，
          <br />
          <em>随时说。</em>
        </h1>
        <p className={styles.lede}>
          真人客服在工作时间在线，平均 40 秒接通。订单、退换、物流，都可以直接问。
        </p>

        <div className={styles.presence}>
          <span className={styles.dot} />
          <div>
            <div className={styles.presenceTitle}>人工客服在线</div>
            <div className={styles.presenceMeta}>当前排队 2 人 · 预计等待 1 分钟</div>
          </div>
        </div>

        <div className={styles.brandFoot}>
          <strong>服务时间 9:00 – 22:00</strong>
          非服务时间可留言，次日优先处理。
          <br />
          对话内容仅用于本次服务。
        </div>
      </aside>

      <section className={styles.pane}>
        <form className={styles.card} onSubmit={handleSubmit} aria-busy={busy}>
          <p className={styles.kicker}>CUSTOMER CENTER</p>
          <h2 className={styles.title}>登录客服中心</h2>
          <p className={styles.sub}>使用你的客户账号登录，继续之前的对话。</p>

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
                账号
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

            <p className={styles.rate}>连续 5 次失败将锁定 15 分钟</p>

            <Button
              className={styles.submit}
              size="lg"
              type="submit"
              disabled={checking || busy || !username.trim() || !password}
            >
              {busy ? "进入对话中…" : "进入对话"}
            </Button>
          </div>

          <p className={styles.help}>账号由客服中心开通，忘记密码请联系在线客服。</p>

          {process.env.NODE_ENV !== "production" ? (
            <p className={styles.testbox}>
              <b>开发期测试账号</b>：见项目 README，生产环境不展示此提示。
            </p>
          ) : null}
        </form>

        <p className={styles.foot}>对话内容加密传输 · 仅用于本次服务</p>
      </section>
    </main>
  );
}
