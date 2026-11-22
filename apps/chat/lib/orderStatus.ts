/** 订单状态只决定圆点颜色；文字始终来自 OMS 的 status_label（ui-spec 3.10）。 */

type OrderTone = {
  dot: string;
  text: string;
};

const STATUS_TONES: Record<string, OrderTone> = {
  PAID_UNFULFILLED: { dot: "bg-warning", text: "text-warning-ink" },
  FULFILLING: { dot: "bg-warning", text: "text-warning-ink" },
  SHIPPED: { dot: "bg-success", text: "text-text-2" },
  DELIVERED: { dot: "bg-success", text: "text-text-2" },
  CANCELLED: { dot: "bg-text-3", text: "text-text-3" },
};

const NEUTRAL_TONE: OrderTone = { dot: "bg-text-3", text: "text-text-2" };

export function orderStatusTone(order: { order_status: string }): OrderTone {
  return STATUS_TONES[order.order_status] ?? NEUTRAL_TONE;
}

// 可取消状态白名单与服务端 `domain.orders.is_cancelable` 一致；这里只决定
// 按钮显隐，提交前仍由服务端重新判定资格（INV-06）。
const CANCELABLE_STATUSES = new Set(["PAID_UNFULFILLED"]);

export function isCancelable(orderStatus: string): boolean {
  return CANCELABLE_STATUSES.has(orderStatus);
}
