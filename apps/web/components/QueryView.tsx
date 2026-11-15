export type Order = {
  order_id: string;
  item_summary: string;
  order_status: string;
  status_text: string;
  amount_cents: number;
  currency: string;
  created_at: string;
  cancelable: boolean;
};

function amount(order: Order): string {
  const value = (order.amount_cents / 100).toFixed(2);
  return order.currency === "CNY" ? `¥${value}` : `${value} ${order.currency}`;
}

export function QueryView({ orders }: { orders: Order[] }) {
  return (
    <div className="orders">
      {orders.map((order) => (
        <article className="order-card" key={order.order_id}>
          <header>
            <span className="order-id">{order.order_id}</span>
            <span className="pill">{order.status_text}</span>
          </header>
          <p className="order-summary">{order.item_summary}</p>
          <p className="order-amount">{amount(order)}</p>
        </article>
      ))}
    </div>
  );
}
