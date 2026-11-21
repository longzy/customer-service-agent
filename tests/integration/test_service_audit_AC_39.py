"""F-13：审计、限速与审计失败回滚（AC-39）。

- 关键动作写 `service_audit_events`：登录/登出、转人工、领取、接管、回复、关闭、转回。
- 401/403/429 是独立提交的安全事件；审计失败不回写原始响应。
- 审计只追加：行级 UPDATE/DELETE 被数据库触发器拒绝。
- 审计写失败：业务回滚并返回 503 `AUDIT_UNAVAILABLE`。
- 客户消息按 session 限速 30/min；超限 429 且无业务副作用。
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from backend.agent_runtime.model import ChatReply
from backend.api.main import create_app
from backend.audit import (
    AuditRecord,
    AuditUnavailableError,
    SqlAuditWriter,
)
from backend.platform.models import (
    ServiceAuditEvent,
    ServiceConversation,
    ServiceCustomerSession,
    ServiceHandoff,
    ServiceMessage,
)
from tests.integration.customer_support import login_customer
from tests.integration.db_support import rows_of, with_db
from tests.integration.db_utils import db_available
from tests.integration.workspace_support import (
    DEMO_CREDENTIAL,
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
    seed_queued_handoff,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

CUSTOMER_MESSAGES = "/customer/messages"
CLAIM = "/workspace/queue/{handoff_id}/claim"
TAKEOVER = "/workspace/conversations/{conversation_id}/takeover"
REPLY = "/workspace/conversations/{conversation_id}/messages"
CLOSE = "/workspace/conversations/{conversation_id}/close"
RETURN_TO_AI = "/workspace/conversations/{conversation_id}/return-to-ai"
REPLY_TEXT = "您好，我是坐席 1"


class UnexpectedModel:
    """审计用例不应触发模型调用（关键词转人工/排队中消息）。"""

    async def respond(self, _message: str) -> ChatReply:
        raise AssertionError("本用例不应调用模型")


class FailingAuditWriter:
    """审计写失败注入：业务事务内写入抛错，安全事件不拦响应。"""

    async def record(self, _db: Any, _record: AuditRecord) -> None:
        raise AuditUnavailableError

    async def record_security(self, _record: AuditRecord) -> None:
        return None

    async def record_view(self, _record: AuditRecord) -> None:
        raise AuditUnavailableError


class BrokenSecurityWriter:
    """安全事件写失败注入：用于确认 401/403/429 响应不被改写。"""

    async def record(self, _db: Any, _record: AuditRecord) -> None:
        return None

    async def record_security(self, _record: AuditRecord) -> None:
        raise RuntimeError("security audit down")

    async def record_view(self, _record: AuditRecord) -> None:
        return None


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client(audit_writer: Any = None) -> TestClient:
    app = create_app()
    app.state.model_client = UnexpectedModel()
    if audit_writer is not None:
        app.state.audit_writer = audit_writer
    return TestClient(app)


def audit_rows() -> list[ServiceAuditEvent]:
    return sorted(rows_of(ServiceAuditEvent), key=lambda row: (row.created_at, row.id))


def audit_events(event_type: str | None = None) -> list[ServiceAuditEvent]:
    rows = audit_rows()
    if event_type is None:
        return rows
    return [row for row in rows if row.event_type == event_type]


def event_types() -> list[str]:
    return [row.event_type for row in audit_rows()]


def conversation_of(conversation_id: str) -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def handoff_of(handoff_id: str) -> ServiceHandoff:
    return next(row for row in rows_of(ServiceHandoff) if row.id == handoff_id)


def send_customer_message(api: TestClient, content: str, *, key: str) -> Any:
    return api.post(CUSTOMER_MESSAGES, json={"content": content}, headers={"Idempotency-Key": key})


def seed_human_active(
    *,
    handoff_id: str = "ho-1",
    conversation_id: str = "conv-1",
) -> None:
    seed_queued_handoff(
        handoff_id,
        conversation_id=conversation_id,
        customer_id="cust-customer_a",
        status="ACTIVE",
        conversation_status="HUMAN_ACTIVE",
        assigned_employee_id="emp-agent_1",
    )


def test_客户登录与登出写审计_AC_39() -> None:
    with api_client() as api:
        login_customer(api)
        response = api.delete("/customer/sessions")

    assert response.status_code == 204
    login_events = audit_events("customer.login")
    logout_events = audit_events("customer.logout")
    assert len(login_events) == 1
    assert len(logout_events) == 1
    login = login_events[0]
    assert login.tenant_id == "tenant-a"
    assert login.actor_type == "customer"
    assert login.actor_id == "cust-customer_a"
    assert login.entity_type == "customer_session"
    assert login.result_status == "committed"
    assert login.journey_id
    assert login.trace_id
    assert login.metadata_redacted["username"] == "customer_a"
    assert logout_events[0].entity_id == login.entity_id


def test_员工登录与登出写审计_AC_39() -> None:
    with api_client() as api:
        login_employee(api, "agent_1")
        response = api.delete("/workspace/sessions")

    assert response.status_code == 204
    assert len(audit_events("employee.login")) == 1
    assert len(audit_events("employee.logout")) == 1
    login = audit_events("employee.login")[0]
    assert login.actor_type == "employee"
    assert login.actor_id == "emp-agent_1"
    assert login.entity_type == "employee_session"
    assert login.metadata_redacted["username"] == "agent_1"
    assert audit_events("employee.logout")[0].entity_id == login.entity_id


def test_未认证与越权写安全事件审计_AC_39() -> None:
    with api_client() as api:
        unauthorized = api.get("/customer/session")
        forbidden = api.post(
            "/workspace/sessions",
            json={"username": "supervisor_x", "password": DEMO_CREDENTIAL},
        )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 403
    auth_failed = audit_events("auth.failed")
    forbidden_events = audit_events("forbidden")
    assert len(auth_failed) == 1
    assert len(forbidden_events) == 1
    assert auth_failed[0].actor_type == "anonymous"
    assert auth_failed[0].result_status == "denied"
    assert auth_failed[0].metadata_redacted["path"] == "/customer/session"
    assert auth_failed[0].metadata_redacted["status_code"] == 401
    assert forbidden_events[0].result_status == "denied"
    assert forbidden_events[0].metadata_redacted["error_code"] == "FORBIDDEN"
    assert forbidden_events[0].actor_type == "employee"
    assert forbidden_events[0].actor_id == "emp-supervisor_x"
    assert forbidden_events[0].metadata_redacted["username"] == "supervisor_x"


def test_登录限速写rate_limited审计_AC_39() -> None:
    with api_client() as api:
        for _ in range(5):
            response = api.post(
                "/customer/sessions",
                json={"username": "customer_a", "password": "wrong-password"},
            )
            assert response.status_code == 401
        limited = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": "wrong-password"},
        )

    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    auth_failed = audit_events("auth.failed")
    assert len(auth_failed) == 5
    assert all(row.metadata_redacted["username"] == "customer_a" for row in auth_failed)
    rate_limited = audit_events("rate_limited")
    assert len(rate_limited) == 1
    assert rate_limited[0].result_status == "rate_limited"
    assert rate_limited[0].metadata_redacted["error_code"] == "RATE_LIMITED"
    assert rate_limited[0].metadata_redacted["username"] == "customer_a"


def test_安全事件审计失败不影响401_AC_39() -> None:
    with api_client(BrokenSecurityWriter()) as api:
        response = api.get("/customer/session")

    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_INVALID"
    assert audit_rows() == []


def test_转人工领取接管回复关闭写审计_AC_39() -> None:
    with api_client() as api:
        login_customer(api)
        queued = send_customer_message(api, "转人工", key="handoff-1")
        assert queued.status_code == 200
        assert queued.json()["status"] == "QUEUED"
        conversation_id = queued.json()["conversation_id"]

        login_employee(api, "agent_1")
        handoff_id = api.get("/workspace/queue").json()["items"][0]["handoff_id"]
        claimed = api.post(CLAIM.format(handoff_id=handoff_id))
        assert claimed.status_code == 200
        taken = api.post(TAKEOVER.format(conversation_id=conversation_id))
        assert taken.status_code == 200
        replied = api.post(
            REPLY.format(conversation_id=conversation_id),
            json={"content": REPLY_TEXT},
            headers={"Idempotency-Key": "reply-1"},
        )
        assert replied.status_code == 200
        closed = api.post(
            CLOSE.format(conversation_id=conversation_id),
            headers={"Idempotency-Key": "close-1"},
        )
        assert closed.status_code == 200

    conversation = conversation_of(conversation_id)
    events = event_types()
    for expected in (
        "customer.login",
        "message.sent",
        "handoff.created",
        "employee.login",
        "handoff.claimed",
        "conversation.taken_over",
        "message.replied",
        "conversation.closed",
    ):
        assert expected in events, expected

    created = audit_events("handoff.created")[0]
    assert created.entity_id == handoff_id
    assert created.journey_id == conversation.journey_id
    assert created.metadata_redacted["conversation_id"] == conversation_id
    assert audit_events("handoff.claimed")[0].actor_id == "emp-agent_1"
    assert audit_events("conversation.taken_over")[0].journey_id == conversation.journey_id
    assert audit_events("message.replied")[0].metadata_redacted["conversation_id"] == (
        conversation_id
    )
    assert audit_events("conversation.closed")[0].result_status == "committed"
    for row in audit_rows():
        if row.event_type in {
            "customer.login",
            "message.sent",
            "handoff.created",
            "handoff.claimed",
            "conversation.taken_over",
            "message.replied",
            "conversation.closed",
        }:
            assert row.tenant_id == "tenant-a"
            assert row.trace_id


def test_转回AI与客户关闭写审计_AC_39() -> None:
    seed_human_active(handoff_id="ho-return", conversation_id="conv-return")
    with api_client() as api:
        login_employee(api, "agent_1")
        returned = api.post(
            RETURN_TO_AI.format(conversation_id="conv-return"),
            headers={"Idempotency-Key": "return-1"},
        )
        assert returned.status_code == 200

        login_customer(api)
        closed = api.post(
            "/customer/session/close",
            headers={"Idempotency-Key": "customer-close-1"},
        )
        assert closed.status_code == 200

    assert len(audit_events("conversation.returned_to_ai")) == 1
    assert audit_events("conversation.returned_to_ai")[0].journey_id == "journey-conv-return"
    customer_closed = [
        row for row in audit_events("conversation.closed") if row.actor_type == "customer"
    ]
    assert len(customer_closed) == 1
    assert customer_closed[0].actor_id == "cust-customer_a"
    assert customer_closed[0].metadata_redacted["from_status"] == "AI_ACTIVE"
    assert customer_closed[0].metadata_redacted["to_status"] == "CLOSED"


def test_坐席回复重放不重复审计_AC_39() -> None:
    seed_human_active()
    with api_client() as api:
        login_employee(api, "agent_1")
        for _ in range(2):
            response = api.post(
                REPLY.format(conversation_id="conv-1"),
                json={"content": REPLY_TEXT},
                headers={"Idempotency-Key": "reply-1"},
            )
            assert response.status_code == 200

    assert len(audit_events("message.replied")) == 1
    agent_messages = [row for row in rows_of(ServiceMessage) if row.author_type == "agent"]
    assert len(agent_messages) == 1


def test_审计写失败时登录503且不建会话_AC_39() -> None:
    with api_client(FailingAuditWriter()) as api:
        response = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": DEMO_CREDENTIAL},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "AUDIT_UNAVAILABLE"
    assert rows_of(ServiceCustomerSession) == []
    assert rows_of(ServiceConversation) == []


def test_审计写失败时客户消息503且无副作用_AC_39() -> None:
    with api_client() as api:
        login_customer(api)
        normal = api.app.state.audit_writer
        api.app.state.audit_writer = FailingAuditWriter()
        response = send_customer_message(api, "转人工", key="handoff-1")
        api.app.state.audit_writer = normal

    assert response.status_code == 503
    assert response.json()["code"] == "AUDIT_UNAVAILABLE"
    assert rows_of(ServiceMessage) == []
    assert rows_of(ServiceHandoff) == []
    conversation = rows_of(ServiceConversation)[0]
    assert conversation.status == "AI_ACTIVE"


def test_审计写失败时坐席动作503且回滚_AC_39() -> None:
    seed_queued_handoff("ho-1", conversation_id="conv-1")
    with api_client() as api:
        login_employee(api, "agent_1")
        normal = api.app.state.audit_writer

        api.app.state.audit_writer = FailingAuditWriter()
        blocked_claim = api.post(CLAIM.format(handoff_id="ho-1"))
        assert blocked_claim.status_code == 503
        assert handoff_of("ho-1").status == "QUEUED"
        assert conversation_of("conv-1").status == "QUEUED"

        api.app.state.audit_writer = normal
        assert api.post(CLAIM.format(handoff_id="ho-1")).status_code == 200

        api.app.state.audit_writer = FailingAuditWriter()
        blocked_takeover = api.post(TAKEOVER.format(conversation_id="conv-1"))
        assert blocked_takeover.status_code == 503
        assert conversation_of("conv-1").status == "CLAIMED"

        api.app.state.audit_writer = normal
        assert api.post(TAKEOVER.format(conversation_id="conv-1")).status_code == 200

        api.app.state.audit_writer = FailingAuditWriter()
        blocked_reply = api.post(
            REPLY.format(conversation_id="conv-1"),
            json={"content": REPLY_TEXT},
            headers={"Idempotency-Key": "reply-1"},
        )
        assert blocked_reply.status_code == 503
        assert [row for row in rows_of(ServiceMessage) if row.author_type == "agent"] == []

        api.app.state.audit_writer = normal
        assert (
            api.post(
                REPLY.format(conversation_id="conv-1"),
                json={"content": REPLY_TEXT},
                headers={"Idempotency-Key": "reply-1"},
            ).status_code
            == 200
        )

        api.app.state.audit_writer = FailingAuditWriter()
        blocked_close = api.post(
            CLOSE.format(conversation_id="conv-1"),
            headers={"Idempotency-Key": "close-1"},
        )
        assert blocked_close.status_code == 503
        assert conversation_of("conv-1").status == "HUMAN_ACTIVE"

        api.app.state.audit_writer = normal
        closed = api.post(
            CLOSE.format(conversation_id="conv-1"),
            headers={"Idempotency-Key": "close-1"},
        )
        assert closed.status_code == 200

    assert conversation_of("conv-1").status == "CLOSED"


def test_审计写失败时转回AI503且回滚_AC_39() -> None:
    seed_human_active()
    with api_client() as api:
        login_employee(api, "agent_1")
        normal = api.app.state.audit_writer
        api.app.state.audit_writer = FailingAuditWriter()
        response = api.post(
            RETURN_TO_AI.format(conversation_id="conv-1"),
            headers={"Idempotency-Key": "return-1"},
        )
        api.app.state.audit_writer = normal

    assert response.status_code == 503
    assert conversation_of("conv-1").status == "HUMAN_ACTIVE"
    assert conversation_of("conv-1").assigned_employee_id == "emp-agent_1"


def test_审计禁止修改与删除_AC_39() -> None:
    with api_client() as api:
        login_customer(api)

    async def tamper(db: Any) -> None:
        from sqlalchemy import text

        await db.execute(text("UPDATE service_audit_events SET result_status = 'tampered'"))
        await db.commit()

    async def remove(db: Any) -> None:
        from sqlalchemy import text

        await db.execute(text("DELETE FROM service_audit_events"))
        await db.commit()

    with pytest.raises(SQLAlchemyError):
        asyncio.run(with_db(tamper))
    with pytest.raises(SQLAlchemyError):
        asyncio.run(with_db(remove))

    rows = audit_rows()
    assert len(rows) == 1
    assert rows[0].event_type == "customer.login"
    assert rows[0].result_status == "committed"


def test_客户消息限速与无副作用_AC_39(monkeypatch: pytest.MonkeyPatch) -> None:
    # 固定窗口按 wall-clock 对齐；把 now 钉在窗口内靠前位置，避免整套测试跑到
    # 分钟边界时 30 条消息跨窗口导致第 31 条不被限速（偶发 flaky）。
    fixed_now = datetime.now(UTC).replace(second=5, microsecond=0)
    monkeypatch.setattr(
        "backend.identity.customer_sessions.utc_now",
        lambda: fixed_now,
    )
    with api_client() as api:
        login_customer(api)
        first = send_customer_message(api, "转人工", key="k-0")
        assert first.status_code == 200
        conversation_id = first.json()["conversation_id"]
        for index in range(1, 30):
            response = send_customer_message(api, f"消息{index}", key=f"k-{index}")
            assert response.status_code == 200
        limited = send_customer_message(api, "第31条", key="k-30")

    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    customer_messages = [
        row
        for row in rows_of(ServiceMessage)
        if row.conversation_id == conversation_id and row.author_type == "customer"
    ]
    assert len(customer_messages) == 30
    assert all(row.content != "第31条" for row in customer_messages)
    rate_limited = audit_events("rate_limited")
    assert len(rate_limited) == 1
    assert rate_limited[0].actor_type == "customer"
    assert rate_limited[0].actor_id == "cust-customer_a"
    assert len(audit_events("message.sent")) == 30


def test_审计元数据不含消息正文_AC_39() -> None:
    content = "我的手机号 13812345678，请转人工"
    with api_client() as api:
        login_customer(api)
        response = send_customer_message(api, content, key="handoff-1")
        assert response.status_code == 200

    rows = audit_rows()
    assert rows
    for row in rows:
        payload = json.dumps(row.metadata_redacted, ensure_ascii=False)
        assert "13812345678" not in payload
        assert content not in payload
        assert "password" not in payload
        assert "token" not in payload.lower()


def test_长路径未认证也写安全事件_AC_39() -> None:
    """401 安全事件的 entity_id 不能因路径超过 64 字符而丢审计。"""

    long_path = "/workspace/conversations/conv-0123456789abcdef0123456789abcdef/messages"
    assert len(long_path) > 64
    with api_client() as api:
        response = api.get(long_path)

    assert response.status_code == 401
    auth_failed = audit_events("auth.failed")
    assert len(auth_failed) == 1
    assert len(auth_failed[0].entity_id) <= 64
    assert auth_failed[0].metadata_redacted["path"] == long_path


def test_跨源写请求403写forbidden审计_AC_39() -> None:
    with api_client() as api:
        response = api.post(
            "/customer/sessions",
            json={"username": "customer_a", "password": DEMO_CREDENTIAL},
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 403
    forbidden = audit_events("forbidden")
    assert len(forbidden) == 1
    assert forbidden[0].metadata_redacted["status_code"] == 403
    assert forbidden[0].metadata_redacted["error_code"] == "FORBIDDEN"
    assert forbidden[0].metadata_redacted["method"] == "POST"


class FriendlyModel:
    """正常 AI 回复；用于验证 AI 回复也有审计。"""

    async def respond(self, _message: str) -> ChatReply:
        return ChatReply(intent="UNKNOWN", confidence=0.9, reply="您好，我是 AI 客服。")


def test_AI回复写审计_AC_39() -> None:
    with api_client() as api:
        api.app.state.model_client = FriendlyModel()
        login_customer(api)
        response = send_customer_message(api, "你好", key="hello-1")

    assert response.status_code == 200
    assert response.json()["status"] == "AI_ACTIVE"
    ai_events = audit_events("ai.replied")
    assert len(ai_events) == 1
    assert ai_events[0].actor_type == "system"
    assert ai_events[0].entity_id == str(response.json()["messages"][-1]["id"])
    assert ai_events[0].metadata_redacted["conversation_id"]


def test_审计写入使用同事务提交_AC_39() -> None:
    """审计行与业务行同一提交：登录成功后两者都存在。"""

    with api_client() as api:
        login_customer(api)

    assert len(audit_events("customer.login")) == 1
    assert len(rows_of(ServiceCustomerSession)) == 1
    assert len(rows_of(ServiceConversation)) == 1


def test_审计默认实现可构造_AC_39() -> None:
    """默认 writer 仍是 SqlAuditWriter；测试替换不改变生产构造。"""

    app = create_app()
    assert isinstance(app.state.audit_writer, SqlAuditWriter)
