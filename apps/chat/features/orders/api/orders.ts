import { readError } from "@/lib/api-client";

import type { CustomerOrders } from "../types";

// 与 AC-59 的上限一致：列表只展示最近 5 笔，不做分页。
const ORDERS_LIMIT = 5;

export async function getOrders(): Promise<CustomerOrders> {
  const response = await fetch(`/api/customer/orders?limit=${ORDERS_LIMIT}`);
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as CustomerOrders;
}
