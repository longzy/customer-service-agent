"""003 订单查询的多轮场景评测（SCENARIO_MODULE）。

`evals/run.py` 把本文件里带 `_AC_XX` 的测试记为场景；这里只放端到端旅程，
单条 AC 的边界用例仍在 `test_order_query_AC_XX.py`。
"""

import asyncio
from typing import Any

import pytest
from sqlalchemy import delete

from backend.adapters.oms.faults import FaultRule
from backend.platform import metrics
from backend.platform.models import (
    ServiceAiEvent,
    ServiceAuditEvent,
    ServiceHandoff,
    ServiceMessage,
    ToolExecution,
)
from tests.integration.customer_support import rows_of
from tests.integration.db_support import with_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import api_client, login, order_app, send
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

DETAIL = "/workspace/conversations/{conversation_id}"
CLAIM = "/workspace/queue/{handoff_id}/claim"
TAKEOVER = "/workspace/conversations/{conversation_id}/takeover"

ORDER_FIELDS = {
    "order_id",
    "item_summary",
    "order_status",
    "status_label",
    "amount_cents",
    "currency",
    "created_at",
    "created_at_local",
}


async def _clear_tool_executions(db: Any) -> None:
    await db.execute(delete(ToolExecution))
    await db.commit()


@pytest.fixture(autouse=True)
def scenario_data() -> Any:
    prepare_workspace_db()
    asyncio.run(with_db(_clear_tool_executions))
    metrics.reset()
    yield
    cleanup_workspace_db()
    asyncio.run(with_db(_clear_tool_executions))
    metrics.reset()


def order_audits() -> list[ServiceAuditEvent]:
    return [row for row in rows_of(ServiceAuditEvent) if row.event_type == "order.queried"]


def tool_rows() -> list[ToolExecution]:
    return rows_of(ToolExecution)


def only_handoff() -> ServiceHandoff:
    handoffs = rows_of(ServiceHandoff)
    assert len(handoffs) == 1
    return handoffs[0]


def test_客户查单到坐席接管的订单上下文_AC_50() -> None:
    """最近订单 → 单笔查询 → 转人工复用快照 → 坐席详情看到同一份订单。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        recent = send(api, "我的订单").json()
        [recent_message] = [item for item in recent["messages"] if item["author_type"] == "ai"]
        assert len(recent_message["payload"]["orders"]) == 4

        single = send(api, "查 ORD-10001").json()
        [single_message] = [item for item in single["messages"] if item["author_type"] == "ai"]
        assert [order["order_id"] for order in single_message["payload"]["orders"]] == ["ORD-10001"]

        handoff_response = send(api, "转人工").json()
        assert handoff_response["status"] == "QUEUED"
        handoff = only_handoff()
        # 复用最近一次单笔快照，不额外查询 OMS。
        assert handoff.context["order_count"] == 1
        assert [order["order_id"] for order in handoff.context["orders"]] == ["ORD-10001"]

        login_employee(api, "agent_1")
        assert api.post(CLAIM.format(handoff_id=handoff.id)).status_code == 200
        takeover = api.post(TAKEOVER.format(conversation_id=handoff.conversation_id))
        detail = api.get(DETAIL.format(conversation_id=handoff.conversation_id))

    assert takeover.status_code == 200, takeover.text
    workspace = detail.json()["handoff"]
    assert workspace["order_context_status"] == "ok"
    assert workspace["order_count"] == 1
    assert [order["order_id"] for order in workspace["orders"]] == ["ORD-10001"]
    # 列表 + 单笔各一条审计；转人工复用快照不再查询。
    assert len(order_audits()) == 2
    assert len(tool_rows()) == 2


def test_跨客户查单统一查无且不泄密_AC_51() -> None:
    """他人订单与不存在订单的响应一致；候选列表不出现他人订单。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        other = send(api, "查 ORD-20001")
        missing = send(api, "查 ORD-99999")
        candidates = send(api, "查 ORD-10001 和 ORD-10002")

    other_body = other.json()
    missing_body = missing.json()
    assert other_body["status"] == "AI_ACTIVE"
    assert other_body["status"] == missing_body["status"]
    other_reply = [
        item["content"] for item in other_body["messages"] if item["author_type"] == "ai"
    ]
    missing_reply = [
        item["content"] for item in missing_body["messages"] if item["author_type"] == "ai"
    ]
    assert other_reply == missing_reply
    # 客户自己的消息回显不算泄露；AI 回复与载荷里不能出现他人订单号。
    assert all(
        "ORD-20001" not in item["content"]
        for item in other_body["messages"]
        if item["author_type"] != "customer"
    )

    [candidate_message] = [
        item for item in candidates.json()["messages"] if item["author_type"] == "ai"
    ]
    candidate_ids = {order["order_id"] for order in candidate_message["payload"]["orders"]}
    assert candidate_ids == {"ORD-10001", "ORD-10002", "ORD-10003", "ORD-10004"}
    assert "ORD-20001" not in candidate_message["content"]


def test_闲聊带订单不查询不建单_AC_52() -> None:
    """没有查询意图的“订单”只走普通回复：无订单事件、审计与卡片。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "订单")

    body = response.json()
    assert body["status"] == "AI_ACTIVE"
    assert order_audits() == []
    assert not [row for row in rows_of(ServiceAiEvent) if row.event_type == "order_query"]
    assert [item for item in body["messages"] if item["author_type"] == "ai"]
    assert all(item.get("payload") is None for item in body["messages"])
    assert rows_of(ServiceHandoff) == []


def test_订单连续失败转人工的订单上下文_AC_53() -> None:
    """两次 OMS 超时：第一次提示重试，第二次转人工且订单上下文标记不可用。"""
    app = order_app()
    app.state.oms.faults.add(FaultRule(kind="timeout", tool="get_order", times=2))
    with api_client(app) as api:
        login(api)
        first = send(api, "查 ORD-10001")
        second = send(api, "再查 ORD-10001")

    assert first.json()["status"] == "AI_ACTIVE"
    assert second.json()["status"] == "QUEUED"
    handoff = only_handoff()
    assert handoff.reason == "ORDER_QUERY_FAILURE"
    assert handoff.context["order_context_status"] == "failed"
    assert handoff.context["order_count"] == 0
    assert [row.metadata_redacted["result"] for row in order_audits()] == ["timeout", "timeout"]
    assert [row.tool_name for row in tool_rows()] == ["get_order", "get_order"]


def test_订单卡片载荷与审计同链路_AC_58() -> None:
    """卡片字段与服务端白名单一致；审计与工具记录共用 trace。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "查 ORD-10002")

    [message] = [item for item in response.json()["messages"] if item["author_type"] == "ai"]
    [order] = message["payload"]["orders"]
    assert set(order) == ORDER_FIELDS
    assert order["order_id"] == "ORD-10002"
    assert order["amount_cents"] == 69900
    assert order["status_label"] == "备货中"

    [audit] = order_audits()
    [execution] = tool_rows()
    assert audit.metadata_redacted["conversation_id"] == response.json()["conversation_id"]
    assert execution.trace_id == audit.trace_id
    # 消息与审计同 trace，恢复时可按 trace 串联。
    ai_message = [row for row in rows_of(ServiceMessage) if row.author_type == "ai"][0]
    assert ai_message.trace_id == audit.trace_id
