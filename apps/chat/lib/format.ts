/** 金额展示统一入口：接口给整数分，界面只做本地化，避免浮点误差。 */
export function formatAmount(amountCents: number, currency: string): string {
  const value = (amountCents / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const code = currency.toUpperCase();
  return code === "CNY" ? `¥${value}` : `${code} ${value}`;
}
