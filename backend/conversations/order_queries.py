"""客户订单查询：订单号提取、授权网关调用与确定性回复。

- 订单归属只按 `Customer.oms_customer_id` 判定；未绑定直接降级，不调用 OMS。
- 查询经 `ToolGateway`（契约校验、归属闸门、超时、Trace），失败统一归一。
- 回复由模板拼装，只陈述 OMS 返回的白名单摘要字段（plan 3.2/3.4）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from backend.conversations.handoffs import ORDER_ID_PATTERN
from backend.identity import Identity
from backend.identity.customer_sessions import Customer
from backend.tools.gateway import GatewayError, ToolGateway

LOCAL_ZONE = ZoneInfo("Asia/Shanghai")

NOT_FOUND_REPLY = "没有查到你名下的这笔订单，请核对订单号，或说「转人工」。"
UNAVAILABLE_REPLY = "订单查询暂时不可用，可以重试，或说「转人工」。"

STATUS_LABELS = {
    "PAID_UNFULFILLED": "已支付未发货",
    "FULFILLING": "备货中",
    "SHIPPED": "已发货",
    "DELIVERED": "已送达",
    "CANCELLED": "已取消",
}

# 订单摘要白名单：items/paid_at/shipped_at 等不进消息、快照、审计或日志。
SUMMARY_FIELDS = (
    "order_id",
    "item_summary",
    "order_status",
    "amount_cents",
    "currency",
    "created_at",
)


def extract_order_ids(text: str) -> list[str]:
    """按出现顺序提取去重后的订单号；大小写归一为 `ORD-...`。"""
    seen: dict[str, None] = {}
    for match in ORDER_ID_PATTERN.findall(text):
        seen.setdefault(match.upper(), None)
    return list(seen)


def format_amount(amount_cents: int, currency: str) -> str:
    """金额格式：CNY 用 `¥`，其他币种保留代码前缀。"""
    value = f"{amount_cents / 100:.2f}"
    if currency.upper() == "CNY":
        return f"¥{value}"
    return f"{currency.upper()} {value}"


def format_created_at(value: str) -> str:
    """把 OMS 的 ISO 时间（含 Z/偏移）转成上海本地时间；解析失败回退原文。"""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(LOCAL_ZONE).strftime("%Y-%m-%d %H:%M")


def order_summary(order: dict[str, Any]) -> dict[str, Any]:
    """把 OMS 订单详情投影为可展示摘要；缺字段时按空值兜底，不抛给调用方。"""
    status = str(order.get("order_status", ""))
    return {
        "order_id": str(order.get("order_id", "")),
        "item_summary": str(order.get("item_summary", "")),
        "order_status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "amount_cents": int(order.get("amount_cents", 0)),
        "currency": str(order.get("currency", "CNY")),
        "created_at": str(order.get("created_at", "")),
        "created_at_local": format_created_at(str(order.get("created_at", ""))),
    }


def build_order_reply(summary: dict[str, Any]) -> str:
    """单笔订单的确定性回复；只使用摘要字段。"""
    amount = format_amount(int(summary["amount_cents"]), str(summary["currency"]))
    return (
        f"你的订单 {summary['order_id']}：{summary['item_summary']}，"
        f"{summary['status_label']}，金额 {amount}，"
        f"下单时间 {summary['created_at_local']}。"
    )


@dataclass(frozen=True)
class OrderQueryOutcome:
    """一次订单查询的结果；`status` 直接写入 `service_ai_events.status`。"""

    status: str  # ok | not_found | unavailable | unbound
    orders: list[dict[str, Any]] = field(default_factory=list)
    reply: str = NOT_FOUND_REPLY
    error_code: str | None = None
    tool: str = "get_order"


def _identity(customer: Customer) -> Identity:
    return Identity(
        account_id=customer.id,
        user_id=customer.oms_customer_id or "",
        tenant_id=customer.tenant_id,
        display_name=customer.display_name,
        tenant_name="",
    )


def _error_code(error: GatewayError) -> str | None:
    code = error.payload.get("code")
    return str(code) if code is not None else None


async def query_order(
    gateway: ToolGateway | None,
    customer: Customer,
    order_id: str,
    trace_id: str,
) -> OrderQueryOutcome:
    """查询客户本人的一笔订单；任何失败都不向客户泄露差异。"""
    if not customer.oms_customer_id:
        return OrderQueryOutcome(status="unbound", orders=[], reply=NOT_FOUND_REPLY)
    if gateway is None:
        return OrderQueryOutcome(
            status="unavailable", orders=[], reply=UNAVAILABLE_REPLY, error_code="GATEWAY_MISSING"
        )
    try:
        order = await asyncio.to_thread(
            gateway.invoke,
            "get_order",
            {"order_id": order_id},
            _identity(customer),
            trace_id,
        )
    except GatewayError as error:
        if error.status_code == 404:
            return OrderQueryOutcome(status="not_found", orders=[], reply=NOT_FOUND_REPLY)
        return OrderQueryOutcome(
            status="unavailable",
            orders=[],
            reply=UNAVAILABLE_REPLY,
            error_code=_error_code(error),
        )
    except Exception:  # noqa: BLE001 - 订单查询失败不能拖垮消息路径
        return OrderQueryOutcome(
            status="unavailable", orders=[], reply=UNAVAILABLE_REPLY, error_code="INTERNAL_ERROR"
        )
    if not isinstance(order, dict):
        return OrderQueryOutcome(
            status="unavailable", orders=[], reply=UNAVAILABLE_REPLY, error_code="INVALID_RESPONSE"
        )
    summary = order_summary(order)
    return OrderQueryOutcome(status="ok", orders=[summary], reply=build_order_reply(summary))
