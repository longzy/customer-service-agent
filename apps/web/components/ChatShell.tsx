"use client";

/**
 * M1 页面骨架：只实现空态与输入区。
 * 消息流、确认卡片与状态切换由 T-10 实现，规则见 ui.md。
 */
export function ChatShell() {
  return (
    <main className="app">
      <header className="topbar">
        <span className="dot" aria-hidden="true" />
        <h1>客服中心</h1>
        <button type="button" className="ghost">
          转人工
        </button>
      </header>

      <div className="log">
        <p className="msg">您好，我可以帮您查询订单，或取消未发货的订单。</p>
        <div className="hints">
          <span>查询订单</span>
          <span>取消订单</span>
        </div>
      </div>

      <div className="composer">
        <label className="sr-only" htmlFor="message">
          输入消息
        </label>
        <textarea id="message" className="cin" placeholder="输入消息" rows={2} />
        <div className="cbar">
          <span className="hint">Enter 发送</span>
          <button type="button" className="send" aria-label="发送">
            发送
          </button>
        </div>
      </div>
    </main>
  );
}
