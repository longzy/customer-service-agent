"""F-25：订单摘要、订单号提取与回复文案的纯函数/分支用例（AC-51）。"""

import pytest

from backend.conversations.order_queries import (
    MULTIPLE_ORDERS_REPLY,
    NOT_FOUND_REPLY,
    PARTIAL_ORDER_ID_REPLY,
    RECENT_EMPTY_REPLY,
    UNAVAILABLE_REPLY,
    OrderQueryOutcome,
    build_order_reply,
    build_recent_orders_reply,
    customer_order_summary,
    extract_order_ids,
    format_amount,
    format_created_at,
    has_non_query_order_intent,
    order_query_audit,
    order_query_kind,
    order_summary,
    query_order,
    query_recent_orders,
    wants_recent_orders,
)
from backend.identity.customer_sessions import Customer
from backend.tools.gateway import GatewayError

ORDER = {
    "order_id": "ORD-10001",
    "item_summary": "无线耳机 × 1",
    "order_status": "PAID_UNFULFILLED",
    "amount_cents": 39900,
    "currency": "CNY",
    "created_at": "2026-11-10T02:00:00Z",
}


def customer(oms_customer_id: str | None = "user-a1") -> Customer:
    return Customer(
        id="cust-customer_a",
        tenant_id="tenant-a",
        username="customer_a",
        display_name="客户甲",
        oms_customer_id=oms_customer_id,
    )


class FakeGateway:
    def __init__(self, result: object = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, object], str]] = []

    def invoke(
        self, name: str, payload: dict[str, object], identity: object, trace_id: str
    ) -> object:
        self.calls.append((name, payload, self.user_id(identity)))
        if self.error is not None:
            raise self.error
        return self.result

    @staticmethod
    def user_id(identity: object) -> str:
        return str(getattr(identity, "user_id", ""))


def test_extract_order_ids_大小写与去重() -> None:
    assert extract_order_ids("查 ORD-10001") == ["ORD-10001"]
    assert extract_order_ids("ord-10001 和 ORD-10001") == ["ORD-10001"]
    assert extract_order_ids("ORD-10001 与 ORD-10002") == ["ORD-10001", "ORD-10002"]
    assert extract_order_ids("我的订单到哪了") == []


def test_extract_order_ids_不误吞相邻数字() -> None:
    assert extract_order_ids("ORD-1000123456789") == []
    assert extract_order_ids("XORD-10001") == []
    assert extract_order_ids("ORD-10001号") == ["ORD-10001"]


def test_has_non_query_order_intent() -> None:
    assert has_non_query_order_intent("取消 ORD-10001")
    assert has_non_query_order_intent("我要退款")
    assert has_non_query_order_intent("改地址")
    assert has_non_query_order_intent("取 消 ORD-10001")
    assert has_non_query_order_intent("退，款 ORD-10001")
    assert not has_non_query_order_intent("查 ORD-10001")
    assert not has_non_query_order_intent("我的订单到哪了")


def test_order_summary_只保留白名单字段() -> None:
    summary = order_summary(
        {
            **ORDER,
            "items": [{"sku": "SKU-1"}],
            "paid_at": "2026-11-10T02:05:00Z",
            "shipped_at": None,
        }
    )
    assert summary == {
        "order_id": "ORD-10001",
        "item_summary": "无线耳机 × 1",
        "order_status": "PAID_UNFULFILLED",
        "status_label": "已支付未发货",
        "amount_cents": 39900,
        "currency": "CNY",
        "created_at": "2026-11-10T02:00:00Z",
        "created_at_local": "2026-11-10 10:00",
    }
    # 003 的消息 payload 不含 cancelable；列表 DTO 才派生。
    assert "cancelable" not in summary


def test_customer_order_summary_派生cancelable() -> None:
    summary = customer_order_summary(ORDER)
    assert summary["cancelable"] is True
    assert set(summary) == set(order_summary(ORDER)) | {"cancelable"}


def test_customer_order_summary_未知状态不可取消() -> None:
    summary = customer_order_summary({**ORDER, "order_status": "RETURNING"})
    assert summary["cancelable"] is False


def test_format_amount() -> None:
    assert format_amount(39900, "CNY") == "¥399.00"
    assert format_amount(2900, "CNY") == "¥29.00"
    assert format_amount(2900, "USD") == "USD 29.00"


def test_format_created_at_转上海时区() -> None:
    assert format_created_at("2026-11-10T02:00:00Z") == "2026-11-10 10:00"
    assert format_created_at("2026-11-10T10:00:00+08:00") == "2026-11-10 10:00"


def test_format_created_at_非法输入回退原文() -> None:
    assert format_created_at("not-a-time") == "not-a-time"


def test_build_order_reply_只陈述摘要字段() -> None:
    reply = build_order_reply(order_summary(ORDER))
    assert "ORD-10001" in reply
    assert "无线耳机 × 1" in reply
    assert "已支付未发货" in reply
    assert "¥399.00" in reply
    assert "2026-11-10 10:00" in reply
    assert "SKU" not in reply


def test_固定文案() -> None:
    assert NOT_FOUND_REPLY == "没有查到你名下的这笔订单，请核对订单号，或说「转人工」。"
    assert UNAVAILABLE_REPLY == "订单查询暂时不可用，可以重试，或说「转人工」。"


@pytest.mark.parametrize(
    ("status", "label"),
    [
        ("PAID_UNFULFILLED", "已支付未发货"),
        ("FULFILLING", "备货中"),
        ("SHIPPED", "已发货"),
        ("DELIVERED", "已送达"),
        ("CANCELLED", "已取消"),
    ],
)
def test_状态文案映射(status: str, label: str) -> None:
    assert order_summary({**ORDER, "order_status": status})["status_label"] == label


def test_未知状态原样回显() -> None:
    summary = order_summary({**ORDER, "order_status": "REFUNDING"})
    assert summary["status_label"] == "REFUNDING"


async def test_query_order_成功返回摘要() -> None:
    gateway = FakeGateway(result=dict(ORDER))
    outcome = await query_order(gateway, customer(), "ORD-10001", "trace-1")
    assert outcome.status == "ok"
    assert outcome.orders[0]["order_id"] == "ORD-10001"
    assert "¥399.00" in outcome.reply
    assert gateway.calls[0][2] == "user-a1"


async def test_query_order_未绑定不调用网关() -> None:
    gateway = FakeGateway(result=dict(ORDER))
    outcome = await query_order(gateway, customer(oms_customer_id=None), "ORD-10001", "t")
    assert outcome.status == "not_found"
    assert outcome.reply == NOT_FOUND_REPLY
    assert gateway.calls == []


async def test_query_order_404归一为查无此单() -> None:
    gateway = FakeGateway(error=GatewayError(404, {"code": "NOT_FOUND_OR_UNAUTHORIZED"}))
    outcome = await query_order(gateway, customer(), "ORD-99999", "t")
    assert outcome.status == "not_found"
    assert outcome.reply == NOT_FOUND_REPLY


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(504, "timeout"), (503, "error"), (502, "error"), (500, "error")],
)
async def test_query_order_失败按状态码分级(status_code: int, expected: str) -> None:
    gateway = FakeGateway(error=GatewayError(status_code, {"code": "DOWNSTREAM"}))
    outcome = await query_order(gateway, customer(), "ORD-10001", "t")
    assert outcome.status == expected
    assert outcome.reply == UNAVAILABLE_REPLY


async def test_query_order_网关缺失与非对象响应都归一为error() -> None:
    missing = await query_order(None, customer(), "ORD-10001", "t")
    assert missing.status == "error"
    assert missing.error_code == "GATEWAY_MISSING"

    invalid = await query_order(
        FakeGateway(result=["not", "a", "dict"]), customer(), "ORD-10001", "t"
    )
    assert invalid.status == "error"
    assert invalid.error_code == "INVALID_RESPONSE"


async def test_query_order_未知异常不抛出() -> None:
    outcome = await query_order(
        FakeGateway(error=RuntimeError("boom")), customer(), "ORD-10001", "t"
    )
    assert outcome.status == "error"
    assert outcome.reply == UNAVAILABLE_REPLY


# --- F-26：最近订单、澄清判定与列表文案 -------------------------------------

ORDER2 = {
    "order_id": "ORD-10002",
    "item_summary": "机械键盘 × 1",
    "order_status": "FULFILLING",
    "amount_cents": 69900,
    "currency": "CNY",
    "created_at": "2026-11-11T03:00:00Z",
}


@pytest.mark.parametrize(
    ("content", "kind"),
    [
        ("查 ORD-10001", "single"),
        ("ord-10001", "single"),
        ("ORD-10001 和 ORD-10002", "multiple"),
        ("查 ORD-10", "partial"),
        ("订单号 ORD-", "partial"),
        ("我的订单", "none"),
        ("最近买了什么", "none"),
        ("取消 ORD-10001", "none"),
        ("取消我的订单", "none"),
    ],
)
def test_order_query_kind(content: str, kind: str) -> None:
    assert order_query_kind(content) == kind


def test_build_recent_orders_reply_只陈述摘要字段() -> None:
    reply = build_recent_orders_reply([order_summary(ORDER), order_summary(ORDER2)])
    assert "最近 2 笔订单" in reply
    assert "ORD-10001" in reply
    assert "机械键盘 × 1" in reply
    assert "备货中" in reply
    assert "¥699.00" in reply
    assert "2026-11-11 11:00" in reply
    assert "SKU" not in reply


def test_最近订单与澄清固定文案() -> None:
    assert MULTIPLE_ORDERS_REPLY == "你提到了多个订单号，我不能替你选。先列出你最近的订单："
    assert PARTIAL_ORDER_ID_REPLY == "订单号看起来不完整。先列出你最近的订单："
    assert RECENT_EMPTY_REPLY == "你名下暂时没有订单。需要的话可以说「转人工」。"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("我的订单", True),
        ("帮我查订单", True),
        ("最近买了什么", True),
        ("最近订单", True),
        ("订单", False),
        ("订单到哪了", False),
        ("取消我的订单", False),
        ("查 ORD-10001", False),
        ("我的单位怎么走", False),
        ("我最近买的手机坏了", False),
        ("你好", False),
    ],
)
def test_wants_recent_orders(content: str, expected: bool) -> None:
    assert wants_recent_orders(content) is expected


async def test_query_recent_orders_成功投影摘要且limit为5() -> None:
    gateway = FakeGateway(result=[dict(ORDER), dict(ORDER2)])
    outcome = await query_recent_orders(gateway, customer(), "trace-1")
    assert outcome.status == "ok"
    assert outcome.tool == "list_recent_orders"
    assert [order["order_id"] for order in outcome.orders] == ["ORD-10001", "ORD-10002"]
    assert "最近 2 笔订单" in outcome.reply
    assert gateway.calls == [("list_recent_orders", {"limit": 5}, "user-a1")]


async def test_query_recent_orders_空列表明确告知() -> None:
    outcome = await query_recent_orders(FakeGateway(result=[]), customer(), "t")
    assert outcome.status == "not_found"
    assert outcome.orders == []
    assert outcome.reply == RECENT_EMPTY_REPLY


async def test_query_recent_orders_未绑定不调用网关() -> None:
    gateway = FakeGateway(result=[])
    outcome = await query_recent_orders(gateway, customer(oms_customer_id=None), "t")
    assert outcome.status == "not_found"
    assert outcome.reply == RECENT_EMPTY_REPLY
    assert gateway.calls == []


async def test_query_recent_orders_非列表响应归一error() -> None:
    outcome = await query_recent_orders(FakeGateway(result={"not": "a list"}), customer(), "t")
    assert outcome.status == "error"
    assert outcome.error_code == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(504, "timeout"), (503, "error"), (500, "error")],
)
async def test_query_recent_orders_失败按状态码分级(status_code: int, expected: str) -> None:
    gateway = FakeGateway(error=GatewayError(status_code, {"code": "DOWNSTREAM"}))
    outcome = await query_recent_orders(gateway, customer(), "t")
    assert outcome.status == expected
    assert outcome.reply == UNAVAILABLE_REPLY
    assert outcome.tool == "list_recent_orders"


async def test_query_recent_orders_未知异常不抛出() -> None:
    outcome = await query_recent_orders(FakeGateway(error=RuntimeError("boom")), customer(), "t")
    assert outcome.status == "error"
    assert outcome.reply == UNAVAILABLE_REPLY


async def test_query_recent_orders_超过5条截断() -> None:
    orders = [
        {**ORDER, "order_id": f"ORD-1000{index}", "created_at": ORDER["created_at"]}
        for index in range(1, 8)
    ]
    outcome = await query_recent_orders(FakeGateway(result=orders), customer(), "t")
    assert outcome.status == "ok"
    assert [order["order_id"] for order in outcome.orders] == [
        "ORD-10001",
        "ORD-10002",
        "ORD-10003",
        "ORD-10004",
        "ORD-10005",
    ]


async def test_订单查询带订单号与未绑定事实供审计() -> None:
    """outcome 携带单笔订单号；审计事实不依赖下游响应内容。"""
    outcome = await query_order(FakeGateway(result=ORDER), customer(), "ORD-10001", "t")
    assert outcome.order_id == "ORD-10001"
    assert outcome.unbound is False
    audit = order_query_audit(outcome)
    assert audit.tool == "get_order"
    assert audit.order_id == "ORD-10001"
    assert audit.order_count == 1
    assert audit.result == "ok"
    assert audit.error_code is None


async def test_未绑定客户查询标记unbound() -> None:
    outcome = await query_order(FakeGateway(result=ORDER), customer(None), "ORD-10001", "t")
    assert outcome.status == "not_found"
    assert outcome.unbound is True
    assert order_query_audit(outcome).result == "not_found"


async def test_列表查询审计订单数与空订单号() -> None:
    outcome = await query_recent_orders(FakeGateway(result=[ORDER]), customer(), "t")
    audit = order_query_audit(outcome)
    assert audit.tool == "list_recent_orders"
    assert audit.order_id is None
    assert audit.order_count == 1
    assert OrderQueryOutcome(status="ok").orders == []
