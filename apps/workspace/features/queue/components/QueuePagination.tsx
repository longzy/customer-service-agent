"use client";

import { Pagination } from "@heroui/react";

export const QUEUE_PAGE_SIZE = 10;

type QueuePaginationProps = {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
};

/**
 * 分页并入表格页脚，不再单独占一行 Card.Footer：
 * 表格只有一层外框，页脚只有一条（显示 x/y 条 + 翻页）。
 */
export function QueuePagination({ page, pageCount, onPageChange }: QueuePaginationProps) {
  if (pageCount <= 1) {
    return <span>领取冲突会刷新队列并提示</span>;
  }

  return (
    <Pagination
      aria-label="队列分页"
      size="sm"
      className="w-auto shrink-0 flex-row gap-0.5 [&_.pagination__link]:h-7 [&_.pagination__link]:min-w-7 [&_.pagination__link]:text-xs"
    >
      <Pagination.Previous
        aria-label="上一页"
        isDisabled={page === 1}
        onPress={() => onPageChange(Math.max(1, page - 1))}
      >
        <Pagination.PreviousIcon />
      </Pagination.Previous>
      <Pagination.Content>
        {Array.from({ length: pageCount }, (_, index) => index + 1).map((value) => (
          <Pagination.Item key={value}>
            <Pagination.Link
              aria-label={`第 ${value} 页`}
              isActive={value === page}
              onPress={() => onPageChange(value)}
            >
              {value}
            </Pagination.Link>
          </Pagination.Item>
        ))}
      </Pagination.Content>
      <Pagination.Next
        aria-label="下一页"
        isDisabled={page === pageCount}
        onPress={() => onPageChange(Math.min(pageCount, page + 1))}
      >
        <Pagination.NextIcon />
      </Pagination.Next>
    </Pagination>
  );
}
