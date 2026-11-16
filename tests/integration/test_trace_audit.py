"""Trace 链路与日志/审计脱敏（AC-17、AC-18）。"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.agent_runtime.model import FakeModelClient
from services.api.main import create_app
from services.platform.models import (
    AuditEvent,
    CancellationRequest,
    Conversation,
    Handoff,
    Message,
    ToolExecution,
)
from services.platform.observability import TraceSinkError, load_trace
from services.platform.settings import settings
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


def _client() -> TestClient:
    app = create_app()
    app.state.model_client = FakeModelClient(
        {
            "查 ORD-10001": {"intent": "QUERY_ORDER", "order_id": "ORD-10001"},
            "取消 ORD-10001": {"intent": "CANCEL_ORDER", "order_id": "ORD-10001"},
            "我的手机号 13800138000，查 ORD-10001": {
                "intent": "QUERY_ORDER",
                "order_id": "ORD-10001",
            },
            "查 ORD-10005": {"intent": "QUERY_ORDER", "order_id": "ORD-10005"},
        }
    )
    return TestClient(app)


def _login(api: TestClient) -> None:
    assert api.post("/session", json={"account_id": "zhang-ming"}).status_code == 200


async def _load(trace_id: str, tenant_id: str = "tenant-a"):
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await load_trace(session, trace_id, tenant_id)
    finally:
        await engine.dispose()


async def _cleanup(trace_ids: list[str], conversation_ids: list[str]) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            if conversation_ids:
                await session.execute(
                    delete(Handoff).where(Handoff.conversation_id.in_(conversation_ids))
                )
                await session.execute(
                    delete(Message).where(Message.conversation_id.in_(conversation_ids))
                )
                await session.execute(
                    delete(Conversation).where(Conversation.id.in_(conversation_ids))
                )
            if trace_ids:
                await session.execute(delete(AuditEvent).where(AuditEvent.trace_id.in_(trace_ids)))
                await session.execute(
                    delete(ToolExecution).where(ToolExecution.trace_id.in_(trace_ids))
                )
                await session.execute(
                    delete(CancellationRequest).where(CancellationRequest.trace_id.in_(trace_ids))
                )
            await session.commit()
    finally:
        await engine.dispose()


def test_查询链路可从trace还原_AC_17() -> None:
    with _client() as api:
        _login(api)
        body = api.post("/message", json={"content": "查 ORD-10001"}).json()
        trace_id = body["trace_id"]
        conversation_id = body["conversation_id"]
        view = asyncio.run(_load(trace_id))
        try:
            assert [item["role"] for item in view.messages] == ["user", "assistant"]
            assert view.messages[0]["content"] == "查 ORD-10001"
            assert [item["tool"] for item in view.tool_executions] == ["get_order"]
            assert view.tool_executions[0]["result_status"] == "ok"
            assert view.tool_executions[0]["response_redacted"]["order_id"] == "ORD-10001"
            intents = [
                item for item in view.audit_events if item["event_type"] == "INTENT_CLASSIFIED"
            ]
            assert intents and intents[0]["metadata"]["intent"] == "QUERY_ORDER"
            assert any(item["event_type"] == "REPLY" for item in view.audit_events)
        finally:
            asyncio.run(_cleanup([trace_id], [conversation_id]))


def test_取消链路复用发起trace_AC_17() -> None:
    with _client() as api:
        _login(api)
        body = api.post("/message", json={"content": "取消 ORD-10001"}).json()
        trace_id = body["trace_id"]
        conversation_id = body["conversation_id"]
        task_id = body["cancellation"]["task_id"]
        assert body["cancellation"]["trace_id"] == trace_id
        confirmed = api.post(f"/cancellation-requests/{task_id}/confirm").json()
        assert confirmed["trace_id"] == trace_id
        view = asyncio.run(_load(trace_id))
        try:
            assert view.cancellation is not None
            assert view.cancellation["task_id"] == task_id
            tool_names = [item["tool"] for item in view.tool_executions]
            assert "get_order" in tool_names
            assert "get_cancel_eligibility" in tool_names
            assert "submit_cancel" in tool_names
            event_types = [item["event_type"] for item in view.audit_events]
            assert "WORKFLOW_TRANSITION" in event_types
            assert "CONFIRMATION" in event_types
            transitions = [
                item["metadata"]
                for item in view.audit_events
                if item["event_type"] == "WORKFLOW_TRANSITION"
            ]
            assert {"from_state": "AWAITING_CONFIRMATION", "to_state": "SUBMITTING"} in [
                {key: item.get(key) for key in ("from_state", "to_state")} for item in transitions
            ]
        finally:
            asyncio.run(_cleanup([trace_id], [conversation_id]))


def test_直接创建取消返回trace_AC_17() -> None:
    body = None
    with _client() as api:
        _login(api)
        body = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()
        assert body["trace_id"]
        view = asyncio.run(_load(body["trace_id"]))
        try:
            assert view.cancellation is not None
            assert view.cancellation["task_id"] == body["id"]
            assert view.messages == []
            assert any(item["event_type"] == "WORKFLOW_TRANSITION" for item in view.audit_events)
        finally:
            asyncio.run(_cleanup([body["trace_id"]], []))


def test_重复确认写入幂等事件且不重复提交_AC_17() -> None:
    with _client() as api:
        _login(api)
        created = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()
        trace_id = created["trace_id"]
        task_id = created["id"]
        first = api.post(f"/cancellation-requests/{task_id}/confirm")
        second = api.post(f"/cancellation-requests/{task_id}/confirm")
        assert first.status_code == 200 and second.status_code == 200
        view = asyncio.run(_load(trace_id))
        try:
            confirmation = [
                item for item in view.audit_events if item["event_type"] == "CONFIRMATION"
            ]
            assert len(confirmation) == 2
            assert confirmation[-1]["result_status"] == "idempotent"
            assert [item["tool"] for item in view.tool_executions].count("submit_cancel") == 1
        finally:
            asyncio.run(_cleanup([trace_id], []))


def test_未知trace返回空_AC_17() -> None:
    view = asyncio.run(_load("00000000-0000-0000-0000-000000000000"))
    assert view.empty
    assert view.events == []


def test_跨租户trace查询为空_AC_17() -> None:
    with _client() as api:
        _login(api)
        body = api.post("/message", json={"content": "查 ORD-10001"}).json()
        trace_id = body["trace_id"]
        conversation_id = body["conversation_id"]
        view = asyncio.run(_load(trace_id, "tenant-b"))
        try:
            assert view.empty
        finally:
            asyncio.run(_cleanup([trace_id], [conversation_id]))


def test_消息手机号不入日志与审计_AC_18(caplog) -> None:
    caplog.set_level("INFO")
    with _client() as api:
        _login(api)
        body = api.post("/message", json={"content": "我的手机号 13800138000，查 ORD-10001"}).json()
        trace_id = body["trace_id"]
        conversation_id = body["conversation_id"]
        view = asyncio.run(_load(trace_id))
        try:
            assert "13800138000" not in caplog.text
            audit_text = json.dumps(view.audit_events, ensure_ascii=False)
            tool_text = json.dumps(view.tool_executions, ensure_ascii=False)
            assert "13800138000" not in audit_text
            assert "13800138000" not in tool_text
            assert view.messages[0]["content"].endswith("查 ORD-10001")
        finally:
            asyncio.run(_cleanup([trace_id], [conversation_id]))


def test_原始幂等键只在业务表_AC_18() -> None:
    async def raw_key(trace_id: str) -> str:
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                value = await session.scalar(
                    select(CancellationRequest.idempotency_key).where(
                        CancellationRequest.trace_id == trace_id
                    )
                )
                return str(value)
        finally:
            await engine.dispose()

    with _client() as api:
        _login(api)
        body = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()
        trace_id = body["trace_id"]
        key = asyncio.run(raw_key(trace_id))
        view = asyncio.run(_load(trace_id))
        try:
            audit_text = json.dumps(view.audit_events, ensure_ascii=False)
            assert key not in audit_text
            digests = [
                item["idempotency_key_digest"]
                for item in view.audit_events
                if item["idempotency_key_digest"]
            ]
            assert digests and all(len(item) == 16 for item in digests)
        finally:
            asyncio.run(_cleanup([trace_id], []))


def test_审计失败返回500而不是200_AC_18(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise TraceSinkError("审计写入失败")

    monkeypatch.setattr("services.platform.observability.AsyncTraceSink.start", fail)
    with _client() as api:
        _login(api)
        response = api.post("/message", json={"content": "查 ORD-10001"})
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"


def test_取消审计失败返回500而不是200_AC_18(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise TraceSinkError("审计写入失败")

    monkeypatch.setattr("services.api.cancellation_routes.audit_transition", fail)
    with _client() as api:
        _login(api)
        response = api.post("/cancellation-requests", json={"order_id": "ORD-10001"})
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"


def test_show_trace_cli_未知trace退出码1_AC_17() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/show-trace.py",
            "--trace-id",
            "00000000-0000-0000-0000-000000000000",
            "--tenant-id",
            "tenant-a",
        ],
        capture_output=True,
        text=True,
        env=os.environ,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode == 1
    assert '"events": []' in result.stdout


def test_超时恢复链路同trace_AC_17() -> None:
    from services.mock_oms.faults import FaultRule

    with _client() as api:
        _login(api)
        api.app.state.oms.faults.add(FaultRule(kind="lost_response", tool="submit_cancel"))
        body = api.post("/message", json={"content": "取消 ORD-10001"}).json()
        trace_id = body["trace_id"]
        conversation_id = body["conversation_id"]
        task_id = body["cancellation"]["task_id"]
        confirmed = api.post(f"/cancellation-requests/{task_id}/confirm").json()
        assert confirmed["trace_id"] == trace_id
        assert confirmed["state"] in {"ACCEPTED", "CANCELLED"}
        view = asyncio.run(_load(trace_id))
        try:
            tool_names = [item["tool"] for item in view.tool_executions]
            assert "submit_cancel" in tool_names
            assert "get_cancel_result" in tool_names
            assert view.cancellation["task_id"] == task_id
            assert view.cancellation["trace_id"] == trace_id
            assert any(
                item["tool"] == "submit_cancel" and item["result_status"] == "failed"
                for item in view.tool_executions
            )
            transitions = [
                item["metadata"]["to_state"]
                for item in view.audit_events
                if item["event_type"] == "WORKFLOW_TRANSITION"
            ]
            assert "SUBMIT_UNKNOWN" in transitions
        finally:
            api.app.state.oms.faults.clear()
            asyncio.run(_cleanup([trace_id], [conversation_id]))


def test_越权拒绝写入trace_AC_17() -> None:
    with _client() as api:
        _login(api)
        body = api.post("/message", json={"content": "查 ORD-10005"}).json()
        trace_id = body["trace_id"]
        conversation_id = body["conversation_id"]
        view = asyncio.run(_load(trace_id))
        try:
            assert view.tool_executions[0]["tool"] == "get_order"
            assert view.tool_executions[0]["result_status"] == "rejected"
            assert view.tool_executions[0]["error_code"] == "NOT_FOUND_OR_UNAUTHORIZED"
            assert view.tool_executions[0]["response_redacted"] is None
        finally:
            asyncio.run(_cleanup([trace_id], [conversation_id]))


def test_确认审计失败不推进状态_AC_18(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise TraceSinkError("审计写入失败")

    with _client() as api:
        _login(api)
        created = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()
        trace_id = created["trace_id"]
        task_id = created["id"]
        monkeypatch.setattr("services.api.cancellation_routes.audit_confirmation", fail)
        response = api.post(f"/cancellation-requests/{task_id}/confirm")
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"

        async def current_state() -> str:
            engine = create_async_engine(settings.database_url)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    value = await session.scalar(
                        select(CancellationRequest.state).where(CancellationRequest.id == task_id)
                    )
                    return str(value)
            finally:
                await engine.dispose()

        try:
            assert asyncio.run(current_state()) == "AWAITING_CONFIRMATION"
        finally:
            asyncio.run(_cleanup([trace_id], []))


def test_创建审计失败不落任务_AC_18(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise TraceSinkError("审计写入失败")

    async def count_tasks() -> int:
        engine = create_async_engine(settings.database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                rows = (
                    await session.execute(
                        select(CancellationRequest.id).where(
                            CancellationRequest.order_id == "ORD-10001"
                        )
                    )
                ).scalars()
                return len(list(rows))
        finally:
            await engine.dispose()

    with _client() as api:
        _login(api)
        before = asyncio.run(count_tasks())
        monkeypatch.setattr("services.api.cancellation_routes.audit_transition", fail)
        response = api.post("/cancellation-requests", json={"order_id": "ORD-10001"})
        assert response.status_code == 500
        after = asyncio.run(count_tasks())
        assert after == before


def test_放弃审计失败不推进状态_AC_18(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise TraceSinkError("审计写入失败")

    with _client() as api:
        _login(api)
        created = api.post("/cancellation-requests", json={"order_id": "ORD-10001"}).json()
        trace_id = created["trace_id"]
        task_id = created["id"]
        monkeypatch.setattr("services.api.cancellation_routes.audit_confirmation", fail)
        response = api.post(f"/cancellation-requests/{task_id}/abandon")
        assert response.status_code == 500

        async def current_state() -> str:
            engine = create_async_engine(settings.database_url)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with factory() as session:
                    value = await session.scalar(
                        select(CancellationRequest.state).where(CancellationRequest.id == task_id)
                    )
                    return str(value)
            finally:
                await engine.dispose()

        try:
            assert asyncio.run(current_state()) == "AWAITING_CONFIRMATION"
        finally:
            asyncio.run(_cleanup([trace_id], []))
