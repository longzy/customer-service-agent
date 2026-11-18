"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api-client";
import { getSession, logout, type Session } from "@/lib/session";

import { getQueue } from "../api/queue";
import { useQueueClaim } from "../hooks/useQueueClaim";
import { useQueueKeyboard } from "../hooks/useQueueKeyboard";
import type { QueueItem } from "../types";

import { DetailPanel } from "./DetailPanel";
import { QueueFallback } from "./QueueFallback";
import { isOverdue } from "./QueueTable";
import { QueueBody } from "./QueueBody";
import { QueueKeyBar } from "./QueueKeyBar";
import { QueueToolbar, type QueueFilter, type QueueSort } from "./QueueToolbar";
import { WorkspaceHeader } from "./WorkspaceHeader";
import { WorkspaceNav } from "./WorkspaceNav";

const ROLE_LABEL: Record<string, string> = { agent: "坐席" };

export function QueueGate() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);

  const [filter, setFilter] = useState<QueueFilter>("all");
  const [reason, setReason] = useState("ALL");
  const [sort, setSort] = useState<QueueSort>("waited");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const searchRef = useRef<HTMLInputElement>(null);
  const initializedRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDenied(false);
    try {
      const current = await getSession();
      if (!current) {
        router.replace("/login");
        return;
      }
      setSession(current);
      const queue = await getQueue();
      if (!queue) {
        router.replace("/login");
        return;
      }
      setItems(queue);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        router.replace("/login");
        return;
      }
      if (cause instanceof ApiError && cause.status === 403) {
        setDenied(true);
        return;
      }
      setError("请求未完成，请重试");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleLogout = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await logout();
      router.replace("/login");
    } catch {
      setError("退出失败，请重试");
    } finally {
      setBusy(false);
    }
  }, [router]);

  const { claimingId, notice, setNotice, claim } = useQueueClaim(load);

  const counts = useMemo(() => {
    const list = items ?? [];
    const overdue = list.filter(isOverdue).length;
    return { all: list.length, waiting: list.length - overdue, overdue };
  }, [items]);

  const visible = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    const list = (items ?? []).filter((item) => {
      if (filter === "waiting" && isOverdue(item)) return false;
      if (filter === "overdue" && !isOverdue(item)) return false;
      if (reason !== "ALL" && item.reason !== reason) return false;
      if (!keyword) return true;
      return (
        item.customer_display_name.toLowerCase().includes(keyword) ||
        item.customer_username.toLowerCase().includes(keyword) ||
        item.last_message.toLowerCase().includes(keyword)
      );
    });
    return list.sort((left, right) =>
      sort === "waited"
        ? right.waiting_seconds - left.waiting_seconds
        : left.waiting_seconds - right.waiting_seconds,
    );
  }, [filter, items, query, reason, sort]);

  useEffect(() => {
    if (!items || visible.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!initializedRef.current) {
      initializedRef.current = true;
      setSelectedId(visible[0].handoff_id);
      return;
    }
    if (selectedId && !visible.some((item) => item.handoff_id === selectedId)) {
      setSelectedId(null);
    }
  }, [items, selectedId, visible]);

  const selected = visible.find((item) => item.handoff_id === selectedId) ?? null;

  useQueueKeyboard({
    visible,
    selectedId,
    selected,
    searchRef,
    onSelect: setSelectedId,
    onClaim: (item) => void claim(item),
    onNotice: setNotice,
  });

  if (!session) {
    return (
      <QueueFallback
        denied={denied}
        error={error}
        loading={loading}
        onRetry={() => void load()}
        onLogout={() => void handleLogout()}
      />
    );
  }

  const { employee } = session;
  const roleLabel = ROLE_LABEL[employee.role] ?? employee.role;

  return (
    <main className="flex min-h-screen bg-bg font-sans">
      <WorkspaceNav
        agentName={employee.display_name}
        roleLabel={roleLabel}
        queueCount={counts.all}
        busy={busy}
        onLogout={() => void handleLogout()}
      />

      <section className="flex min-w-0 flex-1 flex-col bg-bg">
        <WorkspaceHeader
          agentName={employee.display_name}
          total={counts.all}
          overdue={counts.overdue}
          loading={loading}
          query={query}
          searchRef={searchRef}
          onQuery={setQuery}
          onRefresh={() => void load()}
        />

        <div className="flex min-w-0 flex-1 flex-col px-6 max-[1023px]:px-4">
          <QueueToolbar
            filter={filter}
            counts={counts}
            reason={reason}
            sort={sort}
            query={query}
            onFilter={setFilter}
            onReason={setReason}
            onSort={setSort}
            onQuery={setQuery}
            searchRef={searchRef}
          />

          <QueueBody
            items={items}
            visible={visible}
            total={counts.all}
            loading={loading}
            error={error}
            notice={notice}
            selectedId={selectedId}
            claimingId={claimingId}
            disabled={claimingId !== null || loading || busy}
            onRetry={() => void load()}
            onRefresh={() => void load()}
            onClearFilters={() => {
              setQuery("");
              setReason("ALL");
              setFilter("all");
            }}
            onSelect={setSelectedId}
            onClaim={(item) => void claim(item)}
          />

          <QueueKeyBar />
        </div>
      </section>

      <DetailPanel
        item={selected}
        open={Boolean(selected)}
        claiming={claimingId === selected?.handoff_id}
        disabled={claimingId !== null || loading || busy}
        onClaim={() => {
          if (selected) void claim(selected);
        }}
        onClose={() => setSelectedId(null)}
      />
    </main>
  );
}
