import { Suspense } from "react";

import { OrdersPage } from "@/features/orders";

export default function OrdersRoute() {
  return (
    <Suspense
      fallback={
        <main className="grid h-dvh place-items-center bg-bg text-sm text-text-2" role="status">
          正在加载订单
        </main>
      }
    >
      <OrdersPage />
    </Suspense>
  );
}
