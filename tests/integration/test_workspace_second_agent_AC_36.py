"""F-09：第二坐席越权矩阵（AC-36）。

F-07/F-08 已实现条件领取与归属读取；本文件把「第二坐席」作为独立攻击面固定下来：

- 领取他人已领取/已接管的交接单 → 409 `CLAIM_CONFLICT`；
- 查看/接管他人已领取/已接管/已关闭的会话 → 404 `NOT_FOUND`；
- 404 与不存在资源不可区分，失败尝试不改归属/状态/版本，也不写系统消息；
- 归属坐席在第二坐席失败尝试后仍能读取并接管。
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.platform.models import ServiceConversation, ServiceHandoff, ServiceMessage
from tests.integration.db_utils import db_available
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
    rows_of,
    seed_queued_handoff,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

BASE = datetime(2026, 11, 17, 10, 0, 0, tzinfo=UTC)
CLAIM = "/workspace/queue/{handoff_id}/claim"
TAKEOVER = "/workspace/conversations/{conversation_id}/takeover"
DETAIL = "/workspace/conversations/{conversation_id}"
CLAIMING_NOTICE = "正在接入人工"
TAKEOVER_NOTICE = "人工已接入"


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def api_client() -> TestClient:
    return TestClient(create_app())


def claim(api: TestClient, handoff_id: str) -> Any:
    return api.post(CLAIM.format(handoff_id=handoff_id))


def take_over(api: TestClient, conversation_id: str) -> Any:
    return api.post(TAKEOVER.format(conversation_id=conversation_id))


def detail(api: TestClient, conversation_id: str) -> Any:
    return api.get(DETAIL.format(conversation_id=conversation_id))


def handoff_of(handoff_id: str) -> ServiceHandoff:
    return next(row for row in rows_of(ServiceHandoff) if row.id == handoff_id)


def conversation_of(conversation_id: str) -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def system_messages(conversation_id: str) -> list[str]:
    return [
        row.content
        for row in rows_of(ServiceMessage)
        if row.conversation_id == conversation_id and row.author_type == "system"
    ]


def seed_claimed_handoff(*, taken_over: bool = False) -> None:
    """播种一张由 agent_1 领取（可选已接管）的交接单，供第二坐席用例复用。"""
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        created_at=BASE,
        last_message="转人工",
    )
    with api_client() as first:
        login_employee(first, "agent_1")
        assert claim(first, "ho-1").status_code == 200
        if taken_over:
            assert take_over(first, "conv-1").status_code == 200


def test_第二坐席领取已领取单409且归属不变_AC_36() -> None:
    seed_claimed_handoff()

    with api_client() as second:
        login_employee(second, "agent_2")
        response = claim(second, "ho-1")
        queue = second.get("/workspace/queue")

    assert response.status_code == 409
    assert response.json()["code"] == "CLAIM_CONFLICT"
    assert queue.status_code == 200
    assert queue.json()["items"] == []

    handoff = handoff_of("ho-1")
    assert handoff.status == "CLAIMED"
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.version == 1
    conversation = conversation_of("conv-1")
    assert conversation.status == "CLAIMED"
    assert conversation.assigned_employee_id == "emp-agent_1"
    assert system_messages("conv-1").count(CLAIMING_NOTICE) == 1
    assert system_messages("conv-1").count(TAKEOVER_NOTICE) == 0


def test_第二坐席查看已领取会话404且不泄露上下文_AC_36() -> None:
    seed_claimed_handoff()

    with api_client() as second:
        login_employee(second, "agent_2")
        response = detail(second, "conv-1")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    body = response.text
    for leaked in ("customer_a", "客户甲", "转人工", "ho-1"):
        assert leaked not in body


def test_第二坐席接管已领取会话404且归属坐席仍可接管_AC_36() -> None:
    seed_claimed_handoff()

    with api_client() as second:
        login_employee(second, "agent_2")
        response = take_over(second, "conv-1")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    handoff = handoff_of("ho-1")
    assert handoff.status == "CLAIMED"
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.version == 1
    conversation = conversation_of("conv-1")
    assert conversation.status == "CLAIMED"
    assert conversation.assigned_employee_id == "emp-agent_1"
    assert system_messages("conv-1").count(TAKEOVER_NOTICE) == 0

    with api_client() as first:
        login_employee(first, "agent_1")
        read = detail(first, "conv-1")
        taken = take_over(first, "conv-1")

    assert read.status_code == 200
    assert read.json()["status"] == "CLAIMED"
    assert taken.status_code == 200
    assert taken.json() == {"conversation_id": "conv-1", "status": "HUMAN_ACTIVE"}
    assert handoff_of("ho-1").status == "ACTIVE"
    assert conversation_of("conv-1").status == "HUMAN_ACTIVE"
    assert system_messages("conv-1").count(TAKEOVER_NOTICE) == 1


def test_第二坐席查看与接管已接管会话404_AC_36() -> None:
    seed_claimed_handoff(taken_over=True)

    with api_client() as second:
        login_employee(second, "agent_2")
        read = detail(second, "conv-1")
        took_over = take_over(second, "conv-1")

    assert read.status_code == 404
    assert read.json()["code"] == "NOT_FOUND"
    assert took_over.status_code == 404
    assert took_over.json()["code"] == "NOT_FOUND"

    handoff = handoff_of("ho-1")
    assert handoff.status == "ACTIVE"
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.version == 2
    conversation = conversation_of("conv-1")
    assert conversation.status == "HUMAN_ACTIVE"
    assert conversation.assigned_employee_id == "emp-agent_1"
    assert system_messages("conv-1").count(TAKEOVER_NOTICE) == 1


def test_第二坐席领取已接管单409_AC_36() -> None:
    seed_claimed_handoff(taken_over=True)

    with api_client() as second:
        login_employee(second, "agent_2")
        response = claim(second, "ho-1")

    assert response.status_code == 409
    assert response.json()["code"] == "CLAIM_CONFLICT"
    handoff = handoff_of("ho-1")
    assert handoff.status == "ACTIVE"
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.version == 2
    assert conversation_of("conv-1").assigned_employee_id == "emp-agent_1"


def test_第二坐席查看与接管已关闭会话404_AC_36() -> None:
    seed_queued_handoff(
        "ho-1",
        conversation_id="conv-1",
        customer_id="cust-customer_a",
        status="CLOSED",
        conversation_status="CLOSED",
        assigned_employee_id="emp-agent_1",
        created_at=BASE,
    )

    with api_client() as second:
        login_employee(second, "agent_2")
        read = detail(second, "conv-1")
        took_over = take_over(second, "conv-1")

    assert read.status_code == 404
    assert read.json()["code"] == "NOT_FOUND"
    assert took_over.status_code == 404
    assert took_over.json()["code"] == "NOT_FOUND"
    handoff = handoff_of("ho-1")
    assert handoff.status == "CLOSED"
    assert handoff.version == 0
    conversation = conversation_of("conv-1")
    assert conversation.status == "CLOSED"
    assert conversation.assigned_employee_id == "emp-agent_1"


def test_第二坐席404与不存在会话不可区分_AC_36() -> None:
    seed_claimed_handoff()

    with api_client() as second:
        login_employee(second, "agent_2")
        other_detail = detail(second, "conv-1")
        missing_detail = detail(second, "conv-missing")
        other_takeover = take_over(second, "conv-1")
        missing_takeover = take_over(second, "conv-missing")

    for response in (other_detail, missing_detail, other_takeover, missing_takeover):
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"
    assert other_detail.json() == missing_detail.json()
    assert other_takeover.json() == missing_takeover.json()
    assert other_detail.headers["content-type"] == missing_detail.headers["content-type"]
    assert other_takeover.headers["content-type"] == missing_takeover.headers["content-type"]


def test_第二坐席并发接管只有归属者成功_AC_36() -> None:
    seed_claimed_handoff()
    barrier = threading.Barrier(2)

    def attempt(username: str) -> tuple[str, int, dict[str, Any]]:
        with TestClient(create_app()) as api:
            login_employee(api, username)
            barrier.wait(timeout=10)
            response = take_over(api, "conv-1")
            return username, response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ("agent_1", "agent_2")))

    by_agent = {username: (status, body) for username, status, body in results}
    assert by_agent["agent_1"][0] == 200, results
    assert by_agent["agent_2"][0] == 404, results
    assert by_agent["agent_2"][1]["code"] == "NOT_FOUND"

    handoff = handoff_of("ho-1")
    assert handoff.status == "ACTIVE"
    assert handoff.claimed_by == "emp-agent_1"
    assert handoff.version == 2
    conversation = conversation_of("conv-1")
    assert conversation.status == "HUMAN_ACTIVE"
    assert conversation.assigned_employee_id == "emp-agent_1"
    assert system_messages("conv-1").count(TAKEOVER_NOTICE) == 1
