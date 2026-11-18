"use client";

import type { QueueItem } from "../types";

import styles from "./QueueTable.module.css";

export const OVERDUE_SECONDS = 300;

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
};

type QueueTableProps = {
  items: QueueItem[];
  total: number;
  selectedId: string | null;
  claimingId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onClaim: (item: QueueItem) => void;
};

export function formatWait(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, "0")}`;
}

export function isOverdue(item: QueueItem): boolean {
  return item.waiting_seconds >= OVERDUE_SECONDS;
}

export function QueueTable({
  items,
  total,
  selectedId,
  claimingId,
  disabled,
  onSelect,
  onClaim,
}: QueueTableProps) {
  return (
    <div className={styles.card}>
      <table className={styles.table}>
        <colgroup>
          <col style={{ width: 40 }} />
          <col style={{ width: 168 }} />
          <col style={{ width: 70 }} />
          <col style={{ width: 122 }} />
          <col />
          <col style={{ width: 50 }} className={styles.orderCol} />
          <col style={{ width: 78 }} />
          <col style={{ width: 76 }} />
        </colgroup>
        <thead>
          <tr>
            <th>
              <input type="checkbox" className={styles.checkbox} disabled aria-label="批量选择（暂不可用）" />
            </th>
            <th>客户</th>
            <th>等待</th>
            <th>转人工原因</th>
            <th>最后一条消息</th>
            <th className={styles.orderCol} style={{ textAlign: "right" }}>
              订单
            </th>
            <th>状态</th>
            <th style={{ textAlign: "right" }}>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const overdue = isOverdue(item);
            const selected = item.handoff_id === selectedId;
            return (
              <tr
                key={item.handoff_id}
                className={selected ? styles.selected : undefined}
                aria-selected={selected}
                onClick={() => onSelect(item.handoff_id)}
              >
                <td>
                  <input
                    type="checkbox"
                    className={styles.checkbox}
                    disabled
                    aria-label={`选择 ${item.customer_display_name}`}
                  />
                </td>
                <td>
                  <div className={styles.customer}>
                    <span className={styles.avatar} aria-hidden="true">
                      {item.customer_display_name.slice(0, 1)}
                    </span>
                    <span>
                      <span className={styles.name}>{item.customer_display_name}</span>
                      <span className={styles.username}>{item.customer_username}</span>
                    </span>
                  </div>
                </td>
                <td>
                  <span className={overdue ? styles.waitOverdue : styles.wait}>
                    {formatWait(item.waiting_seconds)}
                  </span>
                </td>
                <td className={styles.reason}>{REASON_LABEL[item.reason] ?? item.reason}</td>
                <td className={styles.last}>{item.last_message || "（无客户消息）"}</td>
                <td className={styles.orderCol} style={{ textAlign: "right" }}>
                  <span className={styles.order}>{item.order_count}</span>
                </td>
                <td>
                  <span className={overdue ? styles.stateOverdue : styles.state}>
                    <span className={styles.stateDot} aria-hidden="true" />
                    {overdue ? "已超时" : "等待中"}
                  </span>
                </td>
                <td style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className={selected ? styles.claimPrimary : styles.claim}
                    disabled={disabled}
                    onClick={(event) => {
                      event.stopPropagation();
                      onClaim(item);
                    }}
                    aria-label={`领取 ${item.customer_display_name} 的会话`}
                  >
                    {claimingId === item.handoff_id ? "领取中" : "领取"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className={styles.meta}>
        <span>
          显示 <b>{items.length}</b> / {total} 条
        </span>
        <span className={styles.dot}>·</span>
        <span>队伍按创建时间升序（服务端 FIFO）</span>
        <span className={styles.grow} />
        <span>领取冲突会刷新队列并提示</span>
      </div>
    </div>
  );
}
