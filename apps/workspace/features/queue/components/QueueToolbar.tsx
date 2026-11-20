"use client";

import { ListBox, SearchField, Select, Tabs } from "@heroui/react";
import type { Key, RefObject } from "react";
import { Search } from "lucide-react";

export type QueueFilter = "all" | "waiting" | "overdue";
export type QueueSort = "waited" | "newest";

type QueueToolbarProps = {
  filter: QueueFilter;
  counts: { all: number; waiting: number; overdue: number };
  reason: string;
  sort: QueueSort;
  query: string;
  searchRef: RefObject<HTMLInputElement | null>;
  onFilter: (filter: QueueFilter) => void;
  onReason: (reason: string) => void;
  onSort: (sort: QueueSort) => void;
  onQuery: (query: string) => void;
};

const REASONS = [
  { id: "ALL", label: "全部" },
  { id: "CUSTOMER_REQUEST", label: "客户要求转人工" },
  { id: "LOW_CONFIDENCE", label: "AI 置信度不足" },
  { id: "OUT_OF_SCOPE", label: "超出 AI 处理范围" },
  { id: "MODEL_UNAVAILABLE", label: "模型不可用" },
];

const SORTS = [
  { id: "waited", label: "等待最久" },
  { id: "newest", label: "最新进入" },
];

const TABS: Array<{ value: QueueFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "waiting", label: "等待中" },
  { value: "overdue", label: "已超时" },
];

// 工具条控件统一 34px 高、10px 圆角，标签在框内。
// HeroUI 触发器自带 min-h-9 与 py-2（会顶到 36px 以上），且指示器绝对定位在右 8px，
// 必须保留 pe-7 的让位空间，否则箭头会压在值文本上。
const SELECT_CLASS =
  "h-8 min-h-0 items-center gap-1.5 rounded-lg border border-border bg-surface py-0 ps-2.5 pe-7 text-sm text-text-2 shadow-none";

export function QueueToolbar({
  filter,
  counts,
  reason,
  sort,
  query,
  searchRef,
  onFilter,
  onReason,
  onSort,
  onQuery,
}: QueueToolbarProps) {
  const reasonLabel = REASONS.find((item) => item.id === reason)?.label ?? reason;
  const sortLabel = SORTS.find((item) => item.id === sort)?.label ?? sort;

  return (
    <div className="mt-4 flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-border">
      <Tabs
        variant="secondary"
        selectedKey={filter}
        onSelectionChange={(key) => onFilter(key as QueueFilter)}
        className="shrink-0 [--tab-height:36px] [&_.tabs__list]:gap-6 [&_.tabs__tab]:h-9 [&_.tabs__tab]:px-0 [&_.tabs__tab]:text-sm"
      >
        <Tabs.ListContainer className="border-0">
          <Tabs.List aria-label="队列筛选">
            {TABS.map((tab) => (
              <Tabs.Tab
                key={tab.value}
                id={tab.value}
                aria-label={`${tab.label}，${counts[tab.value]} 个`}
                className="whitespace-nowrap text-sm text-text-3 transition-colors hover:text-text data-[selected]:text-text"
              >
                <span className="inline-flex items-center gap-1.5">
                  {tab.label}
                  <span className="text-xs font-semibold tabular-nums">{counts[tab.value]}</span>
                </span>
                <Tabs.Indicator />
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs.ListContainer>
      </Tabs>

      <div className="mb-2 flex w-full flex-wrap items-center gap-2 min-[768px]:ml-auto min-[768px]:w-auto">
        <SearchField
          aria-label="搜索客户、账号或会话 ID"
          value={query}
          onChange={onQuery}
          className="w-full min-[768px]:w-[280px] min-[768px]:max-[1279px]:w-[220px]"
        >
          <SearchField.Group className="h-8 rounded-lg border-border bg-surface shadow-none focus-within:shadow-focus-field">
            <SearchField.SearchIcon>
              <Search size={14} strokeWidth={1.6} aria-hidden="true" />
            </SearchField.SearchIcon>
            <SearchField.Input
              ref={searchRef}
              placeholder="搜索客户、账号或会话 ID"
              className="text-sm"
            />
            <SearchField.ClearButton aria-label="清空搜索" />
          </SearchField.Group>
        </SearchField>

        {/* RAC 的 SelectInner 只用 Select 根上的 aria-label 判定标签，
            写在外层 Trigger 上会让它每次渲染都打 useLabel 警告；
            根上补基础名，Trigger 上的动态名仍作为读屏实际名称。 */}
        <Select
          aria-label="按原因筛选"
          className="flex-1 min-[768px]:flex-none"
          value={reason}
          onChange={(key) => onReason(key === null ? "ALL" : String(key))}
        >
          {/* 不用 Select.Value：HeroUI 会把值文本拼进 aria-labelledby，
              读屏变成“按原因筛选 全部 原因全部”，这里显式命名控件。 */}
          <Select.Trigger aria-label={`按原因筛选，当前 ${reasonLabel}`} className={SELECT_CLASS}>
            <span aria-hidden="true" className="text-text-3">
              原因
            </span>
            <span className="min-w-0 truncate">{reasonLabel}</span>
            <Select.Indicator />
          </Select.Trigger>
          <Select.Popover>
            <ListBox items={REASONS}>
              {(item) => (
                <ListBox.Item id={item.id} textValue={item.label}>
                  {item.label}
                </ListBox.Item>
              )}
            </ListBox>
          </Select.Popover>
        </Select>

        <Select
          aria-label="排序方式"
          className="flex-1 min-[768px]:flex-none"
          value={sort}
          onChange={(key: Key | null) => {
            if (key === "waited" || key === "newest") onSort(key);
          }}
        >
          <Select.Trigger aria-label={`排序方式，当前 ${sortLabel}`} className={SELECT_CLASS}>
            <span aria-hidden="true" className="text-text-3">
              排序
            </span>
            <span className="min-w-0 truncate">{sortLabel}</span>
            <Select.Indicator />
          </Select.Trigger>
          <Select.Popover>
            <ListBox items={SORTS}>
              {(item) => (
                <ListBox.Item id={item.id} textValue={item.label}>
                  {item.label}
                </ListBox.Item>
              )}
            </ListBox>
          </Select.Popover>
        </Select>
      </div>
    </div>
  );
}
