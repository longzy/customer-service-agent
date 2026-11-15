export type CancellationOrder = {
  order_id: string;
  item_summary: string;
  status_text: string;
  amount_cents: number;
  currency: string;
};

export type Cancellation = {
  task_id: string;
  state: string;
  state_text: string;
  reason_code?: string | null;
  expires_at: string;
  order: CancellationOrder;
};

const ACTIVE = "AWAITING_CONFIRMATION";
const PENDING = new Set(["SUBMITTING", "SUBMIT_UNKNOWN"]);

function amount(order: CancellationOrder): string {
  const value = (order.amount_cents / 100).toFixed(2);
  return order.currency === "CNY" ? `¥${value}` : `${value} ${order.currency}`;
}

export function ConfirmCard({
  cancellation,
  busy,
  onConfirm,
  onAbandon,
}: {
  cancellation: Cancellation;
  busy: boolean;
  onConfirm: () => void;
  onAbandon: () => void;
}) {
  if (cancellation.state !== ACTIVE && !PENDING.has(cancellation.state)) {
    return (
      <div className="confirm-terminal">
        <span className={`pill ${cancellation.state === "CANCELLED" ? "ok" : ""}`}>
          {cancellation.state_text}
        </span>
        <span className="order-id">{cancellation.order.order_id}</span>
        {cancellation.reason_code ? (
          <span className="hint-text">原因：{cancellation.reason_code}</span>
        ) : null}
      </div>
    );
  }

  const pending = PENDING.has(cancellation.state);

  return (
    <section className="confirm-card" aria-label="取消订单确认">
      <header>
        <span>取消订单</span>
        <span className="tag-danger">不可撤销</span>
      </header>
      <div className="confirm-item">
        <span className="order-id">{cancellation.order.order_id}</span>
        <span className="order-summary">{cancellation.order.item_summary}</span>
        <span className="pill">{cancellation.order.status_text}</span>
        <span className="order-amount">{amount(cancellation.order)}</span>
      </div>
      <ul className="confirm-rules">
        <li>提交后不可撤销</li>
        <li>已支付金额原路退回，到账时间以银行为准</li>
        <li>仅未发货订单可以取消</li>
      </ul>
      <p className="confirm-impact">确认后将向订单系统提交取消申请，通常几分钟内完成。</p>
      {pending ? <p className="hint-text">{cancellation.state_text}</p> : null}
      <div className="confirm-actions">
        <button type="button" className="ghost" onClick={onAbandon} disabled={busy}>
          不取消
        </button>
        <button type="button" className="danger" onClick={onConfirm} disabled={busy || pending}>
          确认取消
        </button>
      </div>
    </section>
  );
}
