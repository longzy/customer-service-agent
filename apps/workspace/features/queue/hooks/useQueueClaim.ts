"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api-client";

import { claimHandoff } from "../api/queue";
import type { QueueItem } from "../types";

/** 领取动作：成功跳会话页；404/409 提示并刷新；窄屏只读。 */
export function useQueueClaim(reload: () => Promise<void>) {
  const router = useRouter();
  const [claimingId, setClaimingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const claim = useCallback(
    async (item: QueueItem) => {
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        setNotice("请使用桌面端领取会话");
        return;
      }
      setClaimingId(item.handoff_id);
      setNotice(null);
      try {
        const result = await claimHandoff(item.handoff_id);
        if (!result) {
          router.replace("/login");
          return;
        }
        router.push(`/conversations/${result.conversation_id}`);
      } catch (claimError) {
        if (claimError instanceof ApiError && claimError.status === 404) {
          setNotice("该交接单不存在或已被领取，队列已刷新");
          await reload();
        } else if (claimError instanceof ApiError && claimError.status === 409) {
          setNotice(
            claimError.code === "CONVERSATION_CLOSED"
              ? "该会话已结束"
              : "该会话已被其他坐席领取，队列已刷新",
          );
          await reload();
        } else {
          setNotice("领取失败，请重试");
        }
      } finally {
        setClaimingId(null);
      }
    },
    [reload, router],
  );

  return { claimingId, notice, setNotice, claim };
}
