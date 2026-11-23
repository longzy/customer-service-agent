"""F-34：取消全链路审计与追溯（AC-70）。

- 取消请求、确认、放弃、提交、结果各有审计记录；字段含发起人、确认人、订单、
  任务、结果、错误码与确认来源，不含 PII 与原幂等键。
- 资格/提交/结果三类工具调用在 `tool_executions` 留记录，与审计共用任务链路标识。
- 审计失败返回 503 并回滚业务：不提交、不落确认事实。
- 审计只追加：行级改删被数据库触发器拒绝。
"""

import asyncio
import json
from typing import Any

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import SQLAlchemyError

from backend.adapters.oms.port import OmsAccess
from backend.api.recovery import recover_cancellations
from backend.audit import AuditUnavailableError, SqlAuditWriter
from backend.platform.db import session_factory
from backend.platform.models import ServiceAuditEvent, ToolExecution
from tests.integration.cancellation_support import (
    api_client,
    cancellation_app,
    confirm_cancellation,
    create_cancellation,
    decline_cancellation,
    refresh_cancellation,
    task_rows,
)
from tests.integration.customer_support import cleanup_customer_db, prepare_customer_db, rows_of
from tests.integration.db_support import with_db
from tests.integration.db_utils import db_available
from tests.integration.order_query_support import login, send

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

TENANT = "tenant-a"
CUSTOMER_ID = "cust-customer_a"


class CancellationAuditOnlyFailure:
    """只让 `cancellation.*` 写入失败：验证取消审计自身的 503 回滚路径。"""

    async def record(self, _db: Any, record: Any) -> None:
        if record.event_type.startswith("cancellation."):
            raise AuditUnavailableError

    async def record_security(self, _record: Any) -> None:
        return None

    async def record_view(self, _record: Any) -> None:
        return None


async def _clear_tool_executions(db: Any) -> None:
    await db.execute(delete(ToolExecution))
    await db.commit()


@pytest.fixture(autouse=True)
def demo_customers() -> Any:
    prepare_customer_db()
    asyncio.run(with_db(_clear_tool_executions))
    yield
    cleanup_customer_db()
    asyncio.run(with_db(_clear_tool_executions))


def cancel_events() -> list[ServiceAuditEvent]:
    return [row for row in rows_of(ServiceAuditEvent) if row.event_type.startswith("cancellation.")]


def events_of(event_type: str) -> list[ServiceAuditEvent]:
    return [row for row in cancel_events() if row.event_type == event_type]


def tool_rows() -> list[ToolExecution]:
    return rows_of(ToolExecution)


def test_五类事件齐全且字段在白名单内_AC_70() -> None:
    """请求→确认→提交→结果→刷新：五类事件齐全，字段只含标识与判定结果。"""
    app = cancellation_app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        confirm_cancellation(api, created["id"])
        [row] = task_rows()
        app.state.oms.set_cancel_result(TENANT, row.idempotency_key, "CANCELLED")
        refreshed = refresh_cancellation(api, created["id"])

    assert refreshed.json()["state"] == "CANCELLED"
    events = cancel_events()
    assert [event.event_type for event in events].count("cancellation.requested") == 1
    assert [event.event_type for event in events].count("cancellation.confirmed") == 1
    assert [event.event_type for event in events].count("cancellation.submitted") == 1
    # 已受理与最终已取消各一条结果事件；已受理不是终态。
    results = events_of("cancellation.result")
    assert {event.metadata_redacted["state"] for event in results} == {"ACCEPTED", "CANCELLED"}

    assert {event.entity_type for event in events} == {"cancellation_request"}
    assert {event.entity_id for event in events} == {created["id"]}
    assert {event.tenant_id for event in events} == {TENANT}
    # 同一链路：五类事件共用任务 trace_id。
    assert {event.trace_id for event in events} == {row.trace_id}

    requested = events_of("cancellation.requested")[0]
    assert requested.actor_type == "customer"
    assert requested.actor_id == CUSTOMER_ID
    metadata = requested.metadata_redacted
    assert metadata["task_id"] == created["id"]
    assert metadata["order_id"] == "ORD-10001"
    assert metadata["requested_by_type"] == "CUSTOMER"
    assert metadata["requested_by_id"] == CUSTOMER_ID
    assert metadata["state"] == "AWAITING_CONFIRMATION"

    confirmed = events_of("cancellation.confirmed")[0]
    assert confirmed.actor_type == "customer"
    assert confirmed.actor_id == CUSTOMER_ID
    confirmed_meta = confirmed.metadata_redacted
    assert confirmed_meta["confirmation_source"] == "BUTTON"
    assert confirmed_meta["confirmed_by_id"] == CUSTOMER_ID
    assert confirmed_meta["from_status"] == "AWAITING_CONFIRMATION"
    assert confirmed_meta["to_status"] == "SUBMITTING"

    submitted = events_of("cancellation.submitted")[0]
    assert submitted.actor_type == "system"
    assert submitted.result_status == "ok"
    assert submitted.metadata_redacted["result"] == "accepted"

    accepted = [event for event in results if event.metadata_redacted["state"] == "ACCEPTED"][0]
    assert accepted.metadata_redacted["from_status"] == "SUBMITTING"
    cancelled = [event for event in results if event.metadata_redacted["state"] == "CANCELLED"][0]
    assert cancelled.metadata_redacted["from_status"] == "ACCEPTED"

    # 白名单生效：不含原幂等键，也不含 PII 字段。
    serialized = json.dumps([event.metadata_redacted for event in events], ensure_ascii=False)
    assert row.idempotency_key not in serialized
    for blocked in ("phone", "mobile", "email", "id_card", "password"):
        assert blocked not in serialized


def test_放弃写放弃事件_AC_70() -> None:
    """客户点“不取消”：写放弃事件，不写提交/结果事件，也不调用 OMS 写。"""
    app = cancellation_app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        declined = decline_cancellation(api, created["id"])

    assert declined.json()["state"] == "ABANDONED"
    event_types = [event.event_type for event in cancel_events()]
    assert event_types.count("cancellation.requested") == 1
    assert event_types.count("cancellation.abandoned") == 1
    assert "cancellation.submitted" not in event_types
    assert "cancellation.result" not in event_types
    abandoned = events_of("cancellation.abandoned")[0]
    assert abandoned.metadata_redacted["trigger"] == "customer"
    assert abandoned.metadata_redacted["to_status"] == "ABANDONED"
    assert abandoned.actor_id == CUSTOMER_ID
    assert app.state.oms.calls["submit_cancel"] == 0


def test_工具三类调用同链路_AC_70() -> None:
    """资格/提交/结果三类工具调用都有执行记录，与审计共用同一 trace_id。"""
    app = cancellation_app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        confirm_cancellation(api, created["id"])

    [row] = task_rows()
    executions = tool_rows()
    assert {execution.tool_name for execution in executions} == {
        "get_cancel_eligibility",
        "submit_cancel",
        "get_cancel_result",
    }
    assert {execution.trace_id for execution in executions} == {row.trace_id}
    assert {execution.trace_id for execution in cancel_events()} == {row.trace_id}
    assert {execution.result_status for execution in executions} == {"ok"}
    # 工具记录只留脱敏响应，不写订单明细或金额。
    for execution in executions:
        assert "39900" not in str(execution.response_redacted)


def test_审计失败回滚提交_AC_70() -> None:
    """取消确认时审计写失败：返回 503，确认事实与提交都不推进。"""
    app = cancellation_app()
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()
        api.app.state.audit_writer = CancellationAuditOnlyFailure()
        response = confirm_cancellation(api, created["id"])

    assert response.status_code == 503
    assert response.json()["code"] == "AUDIT_UNAVAILABLE"
    [row] = task_rows()
    # 业务回滚：任务仍在等待确认，确认事实未落库，OMS 没有被提交。
    assert row.state == "AWAITING_CONFIRMATION"
    assert row.confirmed_at is None
    assert row.confirmation_source is None
    assert app.state.oms.calls["submit_cancel"] == 0
    assert events_of("cancellation.confirmed") == []
    assert events_of("cancellation.requested") != []


def test_聊天入口同样写入五类事件_AC_70() -> None:
    """聊天发起与固定短语确认走同一服务：请求带会话，确认来源为 PHRASE。"""
    app = cancellation_app()
    with api_client(app) as api:
        login(api)
        send(api, "查一下 ORD-10001")
        created = send(api, "取消订单").json()
        assert created["messages"][-1]["payload"]["cancellation"]["can_confirm"] is True
        confirmed = send(api, "确认取消")

    [task] = task_rows()
    task_id = task.id
    assert confirmed.status_code == 200, confirmed.text
    requested = events_of("cancellation.requested")
    assert len(requested) == 1
    assert requested[0].metadata_redacted["conversation_id"]
    assert requested[0].entity_id == task_id
    confirmed_event = events_of("cancellation.confirmed")[0]
    assert confirmed_event.metadata_redacted["confirmation_source"] == "PHRASE"
    assert confirmed_event.actor_id == CUSTOMER_ID
    assert events_of("cancellation.submitted")
    assert app.state.oms.calls["submit_cancel"] == 1


def test_取消审计禁止修改与删除_AC_70() -> None:
    """取消审计属只追加密数据：行级 UPDATE/DELETE 被触发器拒绝。"""
    app = cancellation_app()
    with api_client(app) as api:
        login(api)
        create_cancellation(api)

    assert cancel_events()

    async def tamper(db: Any) -> None:
        await db.execute(
            text(
                "UPDATE service_audit_events SET result_status = 'tampered' "
                "WHERE event_type LIKE 'cancellation.%'"
            )
        )
        await db.commit()

    async def remove(db: Any) -> None:
        await db.execute(
            text("DELETE FROM service_audit_events WHERE event_type LIKE 'cancellation.%'")
        )
        await db.commit()

    with pytest.raises(SQLAlchemyError):
        asyncio.run(with_db(tamper))
    with pytest.raises(SQLAlchemyError):
        asyncio.run(with_db(remove))
    assert events_of("cancellation.requested")


async def _force_state(db: Any, task_id: str, state: str) -> None:
    """模拟进程在提交中途重启：任务停在 SUBMITTING，没有进程内状态。"""
    await db.execute(
        text("UPDATE cancellation_requests SET state = :state WHERE id = :id"),
        {"state": state, "id": task_id},
    )
    await db.commit()


def test_启动恢复收敛也写结果事件_AC_70() -> None:
    """重启后收敛悬挂任务同样要写结果事件，否则终态来源不可审计。"""
    app = cancellation_app(max_retries=1, retry_backoff_seconds=0)
    with api_client(app) as api:
        login(api)
        created = create_cancellation(api).json()

    [row] = task_rows()
    # 模拟“提交已到达 OMS、进程随后重启”：先落一次真实提交，再让任务停在 SUBMITTING。
    app.state.oms.submit_cancel(
        OmsAccess(tenant_id=TENANT, user_id="user-a1"), "ORD-10001", row.idempotency_key
    )
    app.state.oms.set_cancel_result(TENANT, row.idempotency_key, "CANCELLED")
    asyncio.run(with_db(lambda db: _force_state(db, created["id"], "SUBMITTING")))
    submits_before = app.state.oms.calls["submit_cancel"]

    async def recover(db: Any) -> int:
        return await recover_cancellations(
            db,
            gateway=app.state.cancel_gateway,
            audit_writer=SqlAuditWriter(session_factory),
            active=app.state.settings,
        )

    assert asyncio.run(with_db(recover)) == 1

    results = events_of("cancellation.result")
    assert [event.metadata_redacted["state"] for event in results] == ["CANCELLED"]
    assert results[0].entity_id == created["id"]
    assert results[0].trace_id == row.trace_id
    assert results[0].metadata_redacted["from_status"] == "SUBMITTING"
    assert results[0].actor_type == "system"
    # 恢复只按幂等键查询，不重复提交。
    assert app.state.oms.calls["submit_cancel"] == submits_before
