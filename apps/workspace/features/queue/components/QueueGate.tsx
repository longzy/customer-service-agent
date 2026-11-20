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
import { QUEUE_PAGE_SIZE } from "./QueuePagination";
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
  const [errorCode, setErrorCode] = useState<string | undefined>(undefined);
  const [denied, setDenied] = useState(false);

  const [filter, setFilter] = useState<QueueFilter>("all");
  const [reason, setReason] = useState("ALL");
  const [sort, setSort] = useState<QueueSort>("waited");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // 抽屉开合与选中解耦：⌘K 可只收起抽屉而保留选中行，供 Enter 领取。
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [page, setPage] = useState(1);

  const searchRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setErrorCode(undefined);
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
      setErrorCode(cause instanceof ApiError ? cause.code : undefined);
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
        item.conversation_id.toLowerCase().includes(keyword) ||
        item.last_message.toLowerCase().includes(keyword)
      );
    });
    return list.sort((left, right) =>
      sort === "waited"
        ? right.waiting_seconds - left.waiting_seconds
        : left.waiting_seconds - right.waiting_seconds,
    );
  }, [filter, items, query, reason, sort]);

  const pageCount = Math.max(1, Math.ceil(visible.length / QUEUE_PAGE_SIZE));
  const pagedVisible = useMemo(
    () => visible.slice((page - 1) * QUEUE_PAGE_SIZE, page * QUEUE_PAGE_SIZE),
    [page, visible],
  );

  useEffect(() => {
    setPage(1);
  }, [filter, reason, sort, query]);

  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);

  // J/K 跨页移动时自动翻到选中行所在页，避免“选中了但看不见”。
  useEffect(() => {
    if (!selectedId) return;
    const index = visible.findIndex((item) => item.handoff_id === selectedId);
    if (index < 0) return;
    const target = Math.floor(index / QUEUE_PAGE_SIZE) + 1;
    if (target !== page) setPage(target);
  }, [page, selectedId, visible]);

  // 抽屉模式下不再默认选中首行（否则加载即弹开抽屉）；仅当已选项被筛掉时清除。
  useEffect(() => {
    if (selectedId && !visible.some((item) => item.handoff_id === selectedId)) {
      setSelectedId(null);
      setDrawerOpen(false);
    }
  }, [selectedId, visible]);

  const handleSelect = useCallback((id: string | null) => {
    setSelectedId(id);
    setDrawerOpen(Boolean(id));
  }, []);

  const selected = visible.find((item) => item.handoff_id === selectedId) ?? null;

  useQueueKeyboard({
    visible,
    selectedId,
    selected,
    searchRef,
    onSelect: handleSelect,
    onDismissDrawer: () => setDrawerOpen(false),
    onClaim: (item) => void claim(item),
    onNotice: setNotice,
  });

  if (!session || denied) {
    return (
      <QueueFallback
        denied={denied}
        error={error}
        errorCode={errorCode}
        loading={loading}
        onRetry={() => void load()}
        onLogout={() => void handleLogout()}
      />
    );
  }

  const { employee } = session;
  const roleLabel = ROLE_LABEL[employee.role] ?? employee.role;

  return (
    <main className="flex h-dvh overflow-hidden bg-bg font-sans">
      <WorkspaceNav
        agentName={employee.display_name}
        roleLabel={roleLabel}
        queueCount={counts.all}
        busy={busy}
        onLogout={() => void handleLogout()}
      />

      <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-bg">
        <header className="shrink-0 bg-surface px-8 max-[1279px]:px-6 max-[1023px]:px-4">
          <WorkspaceHeader
            total={counts.all}
            overdue={counts.overdue}
            loading={loading}
            onRefresh={() => void load()}
          />

          <QueueToolbar
            filter={filter}
            counts={counts}
            reason={reason}
            sort={sort}
            query={query}
            searchRef={searchRef}
            onFilter={setFilter}
            onReason={setReason}
            onSort={setSort}
            onQuery={setQuery}
          />
        </header>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col px-8 pb-2 pt-5 max-[1279px]:px-6 max-[1023px]:px-4">
          <QueueBody
            items={items}
            visible={pagedVisible}
            total={counts.all}
            page={page}
            pageCount={pageCount}
            loading={loading}
            error={error}
            errorCode={errorCode}
            notice={notice}
            selectedId={selectedId}
            claimingId={claimingId}
            disabled={claimingId !== null || loading || busy}
            onPageChange={setPage}
            onRetry={() => void load()}
            onRefresh={() => void load()}
            onClearFilters={() => {
              setQuery("");
              setReason("ALL");
              setFilter("all");
            }}
            onSelect={handleSelect}
            onClaim={(item) => void claim(item)}
          />

          <QueueKeyBar />
        </div>
      </section>

      <DetailPanel
        item={selected}
        open={drawerOpen && Boolean(selected)}
        claiming={claimingId === selected?.handoff_id}
        disabled={claimingId !== null || loading || busy}
        onClaim={() => {
          if (selected) void claim(selected);
        }}
        onClose={() => {
          setDrawerOpen(false);
          setSelectedId(null);
        }}
      />
    </main>
  );
}
