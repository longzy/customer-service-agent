"""读访问审计：主动打开详情记录一次，轮询不记，失败返回 503。"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.api.service_audit import reset_view_dedup
from backend.audit import AuditUnavailableError
from backend.platform.models import ServiceAuditEvent
from tests.integration.customer_support import (
    cleanup_customer_db,
    login_customer,
    prepare_customer_db,
)
from tests.integration.db_support import rows_of
from tests.integration.db_utils import db_available
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
    seed_queued_handoff,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")


@pytest.fixture(autouse=True)
def clean_view_dedup() -> Any:
    reset_view_dedup()
    yield
    reset_view_dedup()


def _view_events() -> list[ServiceAuditEvent]:
    return [
        event for event in rows_of(ServiceAuditEvent) if event.event_type == "conversation.viewed"
    ]


def test_客户重复打开详情只记一条_AC_39() -> None:
    prepare_customer_db()
    try:
        with TestClient(create_app()) as api:
            login = login_customer(api)
            conversation_id = login.json()["conversation"]["id"]
            url = f"/customer/conversations/{conversation_id}"

            assert api.get(url).status_code == 200
            assert api.get(url).status_code == 200

        events = _view_events()
        assert len(events) == 1
        assert events[0].actor_type == "customer"
        assert events[0].entity_type == "conversation"
        assert events[0].entity_id == conversation_id
        assert events[0].result_status == "viewed"
        assert events[0].metadata_redacted["source"] == "customer"
        assert events[0].metadata_redacted["client_ip"]
    finally:
        cleanup_customer_db()


def test_员工打开详情记一条_AC_39() -> None:
    prepare_workspace_db()
    try:
        seed_queued_handoff(
            "ho-view",
            conversation_id="conv-view",
            status="CLAIMED",
            conversation_status="CLAIMED",
            assigned_employee_id="emp-agent_1",
        )
        with TestClient(create_app()) as api:
            login_employee(api)
            url = "/workspace/conversations/conv-view"

            assert api.get(url).status_code == 200
            assert api.get(url).status_code == 200

        events = _view_events()
        assert len(events) == 1
        assert events[0].actor_type == "employee"
        assert events[0].entity_id == "conv-view"
        assert events[0].metadata_redacted["source"] == "workspace"
    finally:
        cleanup_workspace_db()


def test_读访问审计失败返回503_AC_39(monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_customer_db()
    try:
        app = create_app()
        with TestClient(app) as api:
            login = login_customer(api)
            conversation_id = login.json()["conversation"]["id"]

            async def fail(_record: ServiceAuditEvent) -> None:
                raise AuditUnavailableError

            monkeypatch.setattr(app.state.audit_writer, "record_view", fail)
            response = api.get(f"/customer/conversations/{conversation_id}")

        assert response.status_code == 503
        assert response.json()["code"] == "AUDIT_UNAVAILABLE"
    finally:
        cleanup_customer_db()
