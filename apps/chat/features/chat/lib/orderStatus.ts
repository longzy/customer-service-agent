import type { components } from "@/lib/api-types";

export type OrderSummary = components["schemas"]["OrderSummaryPublic"];

type OrderTone = {
  dot: string;
  text: string;
};

/** 订单状态只决定圆点颜色；文字始终来自 OMS 的 status_label（ui-spec 3.10）。 */
const STATUS_TONES: Record<string, OrderTone> = {
  PAID_UNFULFILLED: { dot: "bg-warning", text: "text-warning-ink" },
  FULFILLING: { dot: "bg-warning", text: "text-warning-ink" },
  SHIPPED: { dot: "bg-success", text: "text-text-2" },
  DELIVERED: { dot: "bg-success", text: "text-text-2" },
  CANCELLED: { dot: "bg-text-3", text: "text-text-3" },
};

const NEUTRAL_TONE: OrderTone = { dot: "bg-text-3", text: "text-text-2" };

export function orderStatusTone(order: OrderSummary): OrderTone {
  return STATUS_TONES[order.order_status] ?? NEUTRAL_TONE;
}
