"""F-29：订单查询的审计、工具记录与 Trace 关联（AC-57）。

- 每次订单查询（成功/查无/失败）写一条 `order.queried`：客户、会话、订单号、
  结果；不含订单内容以外的 PII。
- 同一次查询在 `tool_executions` 留工具记录，与审计共用同一 `trace_id`。
- 未绑定 OMS 身份单独记 `order_query_unbound_total`，与"查无"在指标上可区分。
- 审计写失败按既有 503 回滚语义：消息与交接单都不落库。
- 幂等重放没有真实查询，不重复写审计。
"""

import asyncio
from typing import Any

import pytest
from sqlalchemy import delete

from backend.platform import metrics
from backend.platform.models import (
    ServiceAuditEvent,
    ServiceHandoff,
    ServiceMessage,
    ToolExecution,
)
from tests.integration.customer_support import (
    cleanup_customer_db,
    prepare_customer_db,
    rows_of,
)
from tests.integration.db_support import with_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import (
    api_client,
    login,
    order_app,
    send,
    unbind_customer,
)


class OrderAuditOnlyFailure:
    """只让 `order.queried` 写入失败：验证订单审计自身的 503 回滚路径。"""

    async def record(self, _db: Any, record: Any) -> None:
        from backend.audit import AuditUnavailableError

        if record.event_type == "order.queried":
            raise AuditUnavailableError

    async def record_security(self, _record: Any) -> None:
        return None

    async def record_view(self, _record: Any) -> None:
        return None


pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


async def _clear_tool_executions(db: Any) -> None:
    await db.execute(delete(ToolExecution))
    await db.commit()


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    # 工具记录不在客户状态清理范围内；本文件按“本次查询”精确断言，先清空。
    asyncio.run(with_db(_clear_tool_executions))
    yield
    cleanup_customer_db()
    asyncio.run(with_db(_clear_tool_executions))


@pytest.fixture(autouse=True)
def clean_metrics() -> Any:
    metrics.reset()
    yield
    metrics.reset()


def order_audits() -> list[ServiceAuditEvent]:
    return [row for row in rows_of(ServiceAuditEvent) if row.event_type == "order.queried"]


def tool_rows() -> list[ToolExecution]:
    return rows_of(ToolExecution)


def counter(name: str, **labels: str) -> int:
    """按标签字母序拼 key；与 `metrics.snapshot()` 的拍平格式一致。"""
    key = name + "{" + ",".join(f'{item}="{value}"' for item, value in sorted(labels.items())) + "}"
    return metrics.snapshot().get(key, 0)


def test_订单查询写审计与工具记录_AC_57() -> None:
    """单笔成功查询：审计字段齐全，工具记录同 trace，恢复可关联。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "查一下 ORD-10001")
        conversation_id = response.json()["conversation_id"]

    assert response.status_code == 200, response.text
    [audit] = order_audits()
    assert audit.tenant_id == "tenant-a"
    assert audit.actor_type == "customer"
    assert audit.actor_id == "cust-customer_a"
    assert audit.entity_type == "order"
    assert audit.entity_id == "ORD-10001"
    assert audit.result_status == "committed"
    metadata = audit.metadata_redacted
    assert metadata["conversation_id"] == conversation_id
    assert metadata["order_id"] == "ORD-10001"
    assert metadata["order_count"] == 1
    assert metadata["result"] == "ok"
    assert metadata["tool"] == "get_order"

    [execution] = tool_rows()
    assert execution.tool_name == "get_order"
    assert execution.order_id == "ORD-10001"
    assert execution.tenant_id == "tenant-a"
    assert execution.user_id == "user-a1"
    assert execution.result_status == "ok"
    assert execution.latency_ms is not None
    # Trace 关联：审计、工具记录、消息同属一个 trace_id。
    assert execution.trace_id == audit.trace_id
    messages = [row for row in rows_of(ServiceMessage) if row.author_type == "ai"]
    assert messages[0].trace_id == audit.trace_id
    # 工具记录只保留脱敏响应，不写入商品明细与金额。
    assert execution.response_redacted is not None
    assert "items" not in str(execution.response_redacted)
    assert "39900" not in str(execution.response_redacted)
    assert counter("order_query_total", tool="get_order", status="ok") == 1
    assert "order_query_latency_ms_total" in metrics.snapshot()


def test_最近订单查询审计带订单数_AC_57() -> None:
    """列表查询：不写单个订单号，`order_count` 与载荷条数一致。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "我的订单")

    assert response.status_code == 200, response.text
    [audit] = order_audits()
    assert audit.entity_type == "conversation"
    assert audit.entity_id == response.json()["conversation_id"]
    metadata = audit.metadata_redacted
    assert "order_id" not in metadata
    assert metadata["order_count"] == 4
    assert metadata["result"] == "ok"
    assert metadata["tool"] == "list_recent_orders"

    [execution] = tool_rows()
    assert execution.tool_name == "list_recent_orders"
    assert execution.order_id is None
    assert execution.result_status == "ok"
    assert execution.trace_id == audit.trace_id
    assert counter("order_query_total", tool="list_recent_orders", status="ok") == 1


def test_查无订单也写审计与工具记录_AC_57() -> None:
    """他人/不存在：客户看到统一“查无”，审计与工具记录仍保留真实失败原因。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        other = send(api, "查 ORD-20001")
        missing = send(api, "查 ORD-99999")

    assert other.status_code == 200
    assert missing.status_code == 200
    audits = order_audits()
    # 同一请求时间戳相同；审计按 id 排序不稳定，用集合断言。
    assert {row.metadata_redacted["result"] for row in audits} == {"not_found"}
    assert {row.metadata_redacted["order_id"] for row in audits} == {"ORD-20001", "ORD-99999"}
    executions = tool_rows()
    assert {row.tool_name for row in executions} == {"get_order"}
    # 他人与不存在订单都在网关归属闸门被 rejected（不调用 OMS），错误码统一。
    assert {row.result_status for row in executions} == {"rejected"}
    assert {row.error_code for row in executions} == {"NOT_FOUND_OR_UNAUTHORIZED"}
    # 审计、工具记录、AI 消息共用各自请求的 trace。
    assert {row.trace_id for row in audits} == {row.trace_id for row in executions}


def test_未绑定客户查询记unbound_AC_57() -> None:
    """解绑后查询：对客户仍是查无，但指标单独记 unbound，运维可区分。"""
    unbind_customer("customer_a")
    app = order_app()
    with api_client(app) as api:
        login(api)
        response = send(api, "查 ORD-10001")

    assert response.status_code == 200, response.text
    [audit] = order_audits()
    assert audit.metadata_redacted["result"] == "not_found"
    assert audit.metadata_redacted["order_id"] == "ORD-10001"
    assert counter("order_query_unbound_total", tool="get_order") == 1
    # plan 3.2：未绑定不调用 OMS，因此没有工具记录；审计与 unbound 指标仍记录。
    assert tool_rows() == []


def test_审计失败返回503并回滚_AC_57() -> None:
    """订单查询后审计写失败：返回 503，消息与交接单都回滚。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        api.app.state.audit_writer = OrderAuditOnlyFailure()
        response = send(api, "查 ORD-10001")

    assert response.status_code == 503
    assert response.json()["code"] == "AUDIT_UNAVAILABLE"
    # message.sent 已 flush 但同一事务回滚：消息、交接单与审计都不落库。
    assert rows_of(ServiceMessage) == []
    assert rows_of(ServiceHandoff) == []
    event_types = {row.event_type for row in rows_of(ServiceAuditEvent)}
    assert "message.sent" not in event_types
    assert "order.queried" not in event_types


def test_重放不重复审计_AC_57() -> None:
    """同一幂等键重放：返回原消息，不重新查询、不重复审计。"""
    app = order_app()
    with api_client(app) as api:
        login(api)
        first = send(api, "查 ORD-10001", key="order-1")
        second = send(api, "查 ORD-10001", key="order-1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(order_audits()) == 1
    assert len(tool_rows()) == 1
    assert counter("order_query_total", tool="get_order", status="ok") == 1
