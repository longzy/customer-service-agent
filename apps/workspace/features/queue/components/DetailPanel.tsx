"use client";

import type { QueueItem } from "../types";

import { formatWait, isOverdue } from "./QueueTable";
import styles from "./DetailPanel.module.css";

const REASON_LABEL: Record<string, string> = {
  CUSTOMER_REQUEST: "客户要求转人工",
  LOW_CONFIDENCE: "AI 置信度不足",
  OUT_OF_SCOPE: "超出 AI 处理范围",
  MODEL_UNAVAILABLE: "模型不可用",
};

type DetailPanelProps = {
  item: QueueItem | null;
  open: boolean;
  claiming: boolean;
  disabled: boolean;
  onClaim: () => void;
  onClose: () => void;
};

export function DetailPanel({
  item,
  open,
  claiming,
  disabled,
  onClaim,
  onClose,
}: DetailPanelProps) {
  return (
    <aside className={`${styles.detail} ${open ? styles.open : ""}`} aria-label="会话详情">
      <div className={styles.head}>
        <h2 className={styles.title}>会话详情</h2>
        <button
          className={styles.close}
          type="button"
          onClick={onClose}
          aria-label="关闭详情"
          disabled={!item}
        >
          ×
        </button>
      </div>

      {item ? (
        <>
          <div className={styles.customer}>
            <span className={styles.avatar} aria-hidden="true">
              {item.customer_display_name.slice(0, 1)}
            </span>
            <span>
              <span className={styles.name}>
                {item.customer_display_name}
                <span className={styles.tenant}>本租户</span>
              </span>
              <span className={styles.username}>
                {item.customer_username} · 会话 {item.conversation_id.slice(0, 8)}
              </span>
            </span>
          </div>

          <div className={styles.metrics}>
            <div className={styles.metric}>
              <span className={styles.metricLabel}>等待</span>
              <span className={isOverdue(item) ? styles.metricDanger : styles.metricValue}>
                {formatWait(item.waiting_seconds)}
              </span>
            </div>
            <div className={styles.metric}>
              <span className={styles.metricLabel}>转人工原因</span>
              <span className={styles.metricSmall}>
                {REASON_LABEL[item.reason] ?? item.reason}
              </span>
            </div>
            <div className={styles.metric}>
              <span className={styles.metricLabel}>订单</span>
              <span className={styles.metricValue}>{item.order_count}</span>
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionHead}>
              <span>最后一条消息</span>
              <span className={styles.sectionMeta}>已脱敏</span>
            </div>
            <div className={styles.message}>
              <div className={styles.messageHead}>
                <span className={styles.messageWho}>{item.customer_display_name}</span>
              </div>
              <p className={styles.messageBody}>
                {item.last_message || "（无客户消息）"}
              </p>
            </div>
            <div className={styles.mask}>
              <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <rect
                  x="2"
                  y="5"
                  width="8"
                  height="5.5"
                  rx="1.2"
                  stroke="currentColor"
                  strokeWidth="1.2"
                />
                <path d="M4 5V3.8a2 2 0 0 1 4 0V5" stroke="currentColor" strokeWidth="1.2" />
              </svg>
              手机号、邮箱、身份证号已隐藏
            </div>
          </div>

          <div className={styles.section}>
            <div className={styles.sectionHead}>
              <span>完整上下文</span>
              <span className={styles.sectionMeta}>领取后可见</span>
            </div>
            <div className={styles.note}>
              <b>领取后可查看</b>
              <span>最近 20 条消息、AI 轨迹与完整交接摘要。</span>
            </div>
          </div>

          <div className={styles.rules}>
            <b>领取规则</b>
            <span>同一会话仅一名坐席可领取；冲突返回 409 并刷新队列。</span>
            <span>领取后锁定 8 小时，可在「我的会话」中继续。</span>
          </div>

          <div className={styles.actions}>
            <button
              className={styles.claim}
              type="button"
              onClick={onClaim}
              disabled={disabled || claiming}
            >
              {claiming ? "领取中…" : "领取会话"}
            </button>
            <button className={styles.secondary} type="button" disabled title="领取后可查看">
              查看完整交接单
            </button>
            <p className={styles.foot}>
              数据范围：本租户 · 仅坐席可见。超时阈值 5 分钟，超过后在列表中标记。
            </p>
          </div>
        </>
      ) : (
        <div className={styles.empty}>
          <p>选择左侧一行，查看客户与领取规则。</p>
        </div>
      )}
    </aside>
  );
}
