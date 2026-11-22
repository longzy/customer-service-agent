/** 金额展示统一入口：接口给整数分，界面只做本地化，避免浮点误差。 */
export function formatAmount(amountCents: number, currency: string): string {
  const value = (amountCents / 100).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const code = currency.toUpperCase();
  return code === "CNY" ? `¥${value}` : `${code} ${value}`;
}

/** 确认有效期等时间点展示：统一走本地时区，不在组件里散落 toLocaleString。 */
export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
