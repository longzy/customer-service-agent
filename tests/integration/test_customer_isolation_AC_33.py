"""F-14：客户甲/乙端到端闭环与跨客户隔离（AC-33）。

- 甲、乙各自登录、聊天、转人工、被接管、坐席回复、转回 AI、再次转人工、关闭；
  两人的会话与交接单互不影响。
- 甲读乙的会话 404，且与不存在资源不可区分；甲的轮询只返回自己的消息，
  伪造 conversation_id 查询参数、带 conversation_id 的写请求、按消息 id 游标
  都不能读到乙的消息。
- 会话归属按 `(tenant_id, customer_id)`，交接单归属各自 `conversation_id`/`journey_id`。
- 测试数据只通过公开 API 产生，不直接播种会话/交接单；归属断言按执行卡 S-7
  直接读 `service_conversations`/`service_handoffs`/`service_messages`。
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.agent_runtime.model import FakeModelClient
from backend.api.main import create_app
from backend.conversations.statuses import CLOSED, QUEUED
from backend.platform.models import ServiceConversation, ServiceHandoff, ServiceMessage
from tests.integration.customer_support import login_customer
from tests.integration.db_utils import db_available
from tests.integration.workspace_support import (
    cleanup_workspace_db,
    login_employee,
    prepare_workspace_db,
    rows_of,
)

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

CUSTOMER_MESSAGES = "/customer/messages"
CUSTOMER_CLOSE = "/customer/session/close"
QUEUE = "/workspace/queue"
CLAIM = "/workspace/queue/{handoff_id}/claim"
TAKEOVER = "/workspace/conversations/{conversation_id}/takeover"
AGENT_REPLY = "/workspace/conversations/{conversation_id}/messages"
RETURN_TO_AI = "/workspace/conversations/{conversation_id}/return-to-ai"
AGENT_CLOSE = "/workspace/conversations/{conversation_id}/close"
AI_TRANSFER = "转人工"
AI_TAKEOVER_NOTICE = "人工已接入"
AI_QUEUED_NOTICE = "排队中，请稍候"


def model_responses() -> dict[str, dict[str, Any]]:
    return {
        "甲咨询": {"intent": "UNKNOWN", "confidence": 0.95, "reply": "甲您好，我是 AI 客服。"},
        "乙咨询": {"intent": "UNKNOWN", "confidence": 0.95, "reply": "乙您好，我是 AI 客服。"},
        "甲继续": {"intent": "UNKNOWN", "confidence": 0.95, "reply": "甲继续回答。"},
        "乙继续": {"intent": "UNKNOWN", "confidence": 0.95, "reply": "乙继续回答。"},
    }


@pytest.fixture(autouse=True)
def workspace_data() -> Any:
    prepare_workspace_db()
    yield
    cleanup_workspace_db()


def customer_client() -> TestClient:
    app = create_app()
    app.state.model_client = FakeModelClient(model_responses())
    return TestClient(app)


def agent_client() -> TestClient:
    return TestClient(create_app())


def key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def send(client: TestClient, content: str, idempotency_key: str | None = None) -> Any:
    return client.post(
        CUSTOMER_MESSAGES,
        json={"content": content},
        headers={"Idempotency-Key": idempotency_key or key("msg")},
    )


def poll(client: TestClient, after_id: int = 0) -> Any:
    return client.get(CUSTOMER_MESSAGES, params={"after_id": after_id})


def queue(agent: TestClient) -> list[dict[str, Any]]:
    response = agent.get(QUEUE)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def queue_item(agent: TestClient, username: str) -> dict[str, Any]:
    matches = [item for item in queue(agent) if item["customer_username"] == username]
    assert len(matches) == 1, matches
    return matches[0]


def claim(agent: TestClient, handoff_id: str) -> Any:
    response = agent.post(CLAIM.format(handoff_id=handoff_id))
    assert response.status_code == 200, response.text
    return response.json()


def takeover(agent: TestClient, conversation_id: str) -> Any:
    response = agent.post(TAKEOVER.format(conversation_id=conversation_id))
    assert response.status_code == 200, response.text
    return response.json()


def agent_reply(agent: TestClient, conversation_id: str, content: str) -> Any:
    response = agent.post(
        AGENT_REPLY.format(conversation_id=conversation_id),
        json={"content": content},
        headers={"Idempotency-Key": key("agent-reply")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def return_to_ai(agent: TestClient, conversation_id: str) -> Any:
    response = agent.post(
        RETURN_TO_AI.format(conversation_id=conversation_id),
        headers={"Idempotency-Key": key("return")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def close_by_agent(agent: TestClient, conversation_id: str) -> Any:
    response = agent.post(
        AGENT_CLOSE.format(conversation_id=conversation_id),
        headers={"Idempotency-Key": key("agent-close")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def close_by_customer(customer: TestClient) -> Any:
    response = customer.post(CUSTOMER_CLOSE, headers={"Idempotency-Key": key("customer-close")})
    assert response.status_code == 200, response.text
    return response.json()


def contents(response: Any) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["content"] for item in response.json()["messages"]]


def conversation_id_of(client: TestClient) -> str:
    response = client.get("/customer/session")
    assert response.status_code == 200, response.text
    return response.json()["conversation"]["id"]


def transfer(client: TestClient) -> Any:
    response = send(client, AI_TRANSFER)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == QUEUED
    return response.json()


def conversation_of(conversation_id: str) -> ServiceConversation:
    return next(row for row in rows_of(ServiceConversation) if row.id == conversation_id)


def handoffs_of(conversation_id: str) -> list[ServiceHandoff]:
    return sorted(
        (row for row in rows_of(ServiceHandoff) if row.conversation_id == conversation_id),
        key=lambda row: (row.created_at, row.id),
    )


def test_客户甲乙各自完整闭环_AC_33() -> None:
    with (
        customer_client() as customer_a,
        customer_client() as customer_b,
        agent_client() as agent_a,
        agent_client() as agent_b,
    ):
        login_customer(customer_a, "customer_a")
        login_customer(customer_b, "customer_b")

        # 登录即恢复/创建各自的未关闭会话。
        conversation_a = conversation_id_of(customer_a)
        conversation_b = conversation_id_of(customer_b)
        assert conversation_a != conversation_b

        # 聊天：各自拿到 AI 回复，消息不串。
        chat_a = send(customer_a, "甲咨询")
        chat_b = send(customer_b, "乙咨询")
        assert chat_a.status_code == 200, chat_a.text
        assert chat_b.status_code == 200, chat_b.text
        assert contents(chat_a) == ["甲咨询", "甲您好，我是 AI 客服。"]
        assert contents(chat_b) == ["乙咨询", "乙您好，我是 AI 客服。"]

        # 转人工：两张独立 QUEUED 交接单。
        transfer_a = transfer(customer_a)
        transfer_b = transfer(customer_b)
        assert AI_QUEUED_NOTICE in [item["content"] for item in transfer_a["messages"]]
        assert AI_QUEUED_NOTICE in [item["content"] for item in transfer_b["messages"]]

        # 双坐席：甲由 agent_1、乙由 agent_2（plan 5.2 的 2 客户/2 坐席 seam）。
        login_employee(agent_a, "agent_1")
        login_employee(agent_b, "agent_2")
        assert {item["customer_username"] for item in queue(agent_a)} == {
            "customer_a",
            "customer_b",
        }
        handoff_a = queue_item(agent_a, "customer_a")["handoff_id"]
        handoff_b = queue_item(agent_b, "customer_b")["handoff_id"]
        assert handoff_a != handoff_b

        # 甲：被领取、被接管、被回复。
        assert claim(agent_a, handoff_a)["conversation_id"] == conversation_a
        assert takeover(agent_a, conversation_a)["status"] == "HUMAN_ACTIVE"
        assert AI_TAKEOVER_NOTICE in contents(poll(customer_a))
        agent_reply(agent_a, conversation_a, "甲您好，我是坐席 1")
        a_after_reply = poll(customer_a)
        assert a_after_reply.status_code == 200, a_after_reply.text
        assert a_after_reply.json()["messages"][-1]["author_type"] == "agent"
        assert "甲您好，我是坐席 1" in contents(a_after_reply)

        # 乙尚未领取，状态与队列不受甲的动作影响。
        assert poll(customer_b).json()["status"] == QUEUED
        assert queue_item(agent_b, "customer_b")["handoff_id"] == handoff_b

        # 甲：转回 AI 后同一会话继续，历史保留。
        assert return_to_ai(agent_a, conversation_a)["status"] == "AI_ACTIVE"
        chat_again_a = send(customer_a, "甲继续")
        assert chat_again_a.status_code == 200, chat_again_a.text
        assert chat_again_a.json()["conversation_id"] == conversation_a
        assert chat_again_a.json()["messages"][-1]["content"] == "甲继续回答。"
        a_history = contents(poll(customer_a))
        assert "甲咨询" in a_history
        assert "甲您好，我是坐席 1" in a_history
        assert "已转回 AI 客服" in a_history

        # 甲：再次转人工生成新交接单，旧单已关闭。
        transfer(customer_a)
        new_handoff_a = queue_item(agent_a, "customer_a")["handoff_id"]
        assert new_handoff_a != handoff_a
        old_a = next(row for row in handoffs_of(conversation_a) if row.id == handoff_a)
        assert old_a.status == CLOSED
        claim(agent_a, new_handoff_a)
        takeover(agent_a, conversation_a)
        assert close_by_customer(customer_a)["status"] == CLOSED
        assert send(customer_a, "甲还在吗").status_code == 409

        # 乙：同样完整走一轮（由 agent_2 接管），最后由坐席关闭。
        assert claim(agent_b, handoff_b)["conversation_id"] == conversation_b
        assert takeover(agent_b, conversation_b)["status"] == "HUMAN_ACTIVE"
        assert AI_TAKEOVER_NOTICE in contents(poll(customer_b))
        agent_reply(agent_b, conversation_b, "乙您好，我是坐席 2")
        assert "乙您好，我是坐席 2" in contents(poll(customer_b))
        assert return_to_ai(agent_b, conversation_b)["status"] == "AI_ACTIVE"
        chat_again_b = send(customer_b, "乙继续")
        assert chat_again_b.status_code == 200, chat_again_b.text
        assert chat_again_b.json()["messages"][-1]["content"] == "乙继续回答。"
        b_history = contents(poll(customer_b))
        assert "乙咨询" in b_history
        assert "乙您好，我是坐席 2" in b_history
        assert "已转回 AI 客服" in b_history
        transfer(customer_b)
        new_handoff_b = queue_item(agent_b, "customer_b")["handoff_id"]
        assert new_handoff_b != handoff_b
        old_b = next(row for row in handoffs_of(conversation_b) if row.id == handoff_b)
        assert old_b.status == CLOSED
        claim(agent_b, new_handoff_b)
        takeover(agent_b, conversation_b)
        assert close_by_agent(agent_b, conversation_b)["status"] == CLOSED
        assert send(customer_b, "乙还在吗").status_code == 409

    # 每人一个会话、两张交接单（首单转回时终态，次单关闭时终态）。
    a_handoffs = handoffs_of(conversation_a)
    b_handoffs = handoffs_of(conversation_b)
    assert len(a_handoffs) == 2
    assert len(b_handoffs) == 2
    assert {row.status for row in a_handoffs} == {CLOSED}
    assert {row.status for row in b_handoffs} == {CLOSED}
    assert {row.customer_id for row in a_handoffs} == {"cust-customer_a"}
    assert {row.customer_id for row in b_handoffs} == {"cust-customer_b"}
    assert {row.journey_id for row in a_handoffs}.isdisjoint({row.journey_id for row in b_handoffs})

    # 两次转人工仍在同一会话；甲/乙各只有一个会话。
    a_ids = {row.id for row in a_handoffs}
    b_ids = {row.id for row in b_handoffs}
    assert a_ids.isdisjoint(b_ids)
    conversations = {row.id for row in rows_of(ServiceConversation)}
    assert conversations == {conversation_a, conversation_b}

    # 消息按会话隔离：甲的回复不会出现在乙的会话里，反之亦然。
    a_texts = {
        row.content for row in rows_of(ServiceMessage) if row.conversation_id == conversation_a
    }
    b_texts = {
        row.content for row in rows_of(ServiceMessage) if row.conversation_id == conversation_b
    }
    assert "甲您好，我是坐席 1" in a_texts
    assert "乙您好，我是坐席 2" not in a_texts
    assert "乙您好，我是坐席 2" in b_texts
    assert "甲您好，我是坐席 1" not in b_texts


def test_客户甲读客户乙会话与消息404_AC_33() -> None:
    with customer_client() as customer_a, customer_client() as customer_b:
        login_customer(customer_a, "customer_a")
        login_customer(customer_b, "customer_b")
        assert send(customer_a, "甲咨询").status_code == 200
        assert send(customer_b, "乙咨询").status_code == 200
        conversation_a = conversation_id_of(customer_a)
        conversation_b = conversation_id_of(customer_b)

        # 甲的轮询只含自己的消息。
        a_page = poll(customer_a)
        assert "甲咨询" in contents(a_page)
        assert "乙咨询" not in contents(a_page)

        # 甲读乙的会话 404；乙读自己 200。
        other = customer_a.get(f"/customer/conversations/{conversation_b}")
        own = customer_b.get(f"/customer/conversations/{conversation_b}")
        assert other.status_code == 404
        assert other.json()["code"] == "NOT_FOUND"
        assert own.status_code == 200
        assert own.json()["conversation"]["id"] == conversation_b

        # 不存在资源与“乙的会话”对甲不可区分。
        missing = customer_a.get(f"/customer/conversations/{uuid.uuid4()}")
        assert missing.status_code == 404
        assert missing.json() == other.json()

        # 乙读甲的会话同样 404。
        reverse = customer_b.get(f"/customer/conversations/{conversation_a}")
        assert reverse.status_code == 404
        assert reverse.json() == other.json()

        # 消息维度：没有按 conversation_id 读消息的端点；伪造参数/路径/写字段都不能读到乙。
        forged_query = customer_a.get(
            CUSTOMER_MESSAGES,
            params={"conversation_id": conversation_b, "after_id": 0},
        )
        assert forged_query.status_code == 200
        assert "乙咨询" not in contents(forged_query)
        message_path = f"/customer/conversations/{conversation_b}/messages"
        assert customer_a.get(message_path).status_code == 404

        before = len(rows_of(ServiceMessage))
        forged_write = customer_a.post(
            CUSTOMER_MESSAGES,
            json={"content": "甲伪造会话", "conversation_id": conversation_b},
            headers={"Idempotency-Key": key("forged-write")},
        )
        assert forged_write.status_code == 422
        assert len(rows_of(ServiceMessage)) == before

        b_page = poll(customer_b)
        b_last_id = b_page.json()["after_id"]
        cursor = customer_a.get(CUSTOMER_MESSAGES, params={"after_id": b_last_id})
        assert cursor.status_code == 200
        assert all("乙" not in item["content"] for item in cursor.json()["messages"])

    # 未登录读取他人会话 401，不泄露是否存在。
    with TestClient(create_app()) as anonymous:
        unauthorized = anonymous.get(f"/customer/conversations/{conversation_b}")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "SESSION_INVALID"


def test_客户甲关闭不影响客户乙_AC_33() -> None:
    with (
        customer_client() as customer_a,
        customer_client() as customer_b,
        agent_client() as agent,
    ):
        login_customer(customer_a, "customer_a")
        login_customer(customer_b, "customer_b")
        transfer(customer_a)
        transfer(customer_b)
        conversation_a = conversation_id_of(customer_a)
        conversation_b = conversation_id_of(customer_b)
        login_employee(agent, "agent_1")
        handoff_a = queue_item(agent, "customer_a")["handoff_id"]
        handoff_b = queue_item(agent, "customer_b")["handoff_id"]

        assert close_by_customer(customer_a)["status"] == CLOSED
        assert send(customer_a, "甲还在吗").status_code == 409

        # 乙仍排队，且可继续发消息、可被领取。
        assert conversation_of(conversation_b).status == QUEUED
        assert next(row for row in rows_of(ServiceHandoff) if row.id == handoff_b).status == QUEUED
        still_open = send(customer_b, "乙还在吗")
        assert still_open.status_code == 200, still_open.text
        assert "乙还在吗" in contents(still_open)
        assert [item["customer_username"] for item in queue(agent)] == ["customer_b"]

        assert claim(agent, handoff_b)["conversation_id"] == conversation_b
        assert takeover(agent, conversation_b)["status"] == "HUMAN_ACTIVE"
        agent_reply(agent, conversation_b, "乙您好，我是坐席 1")
        assert "乙您好，我是坐席 1" in contents(poll(customer_b))

    # 甲会话与甲交接单已终态；乙仍活着。
    assert conversation_of(conversation_a).status == CLOSED
    closed_a = next(row for row in rows_of(ServiceHandoff) if row.id == handoff_a)
    active_b = next(row for row in rows_of(ServiceHandoff) if row.id == handoff_b)
    assert closed_a.status == CLOSED
    assert active_b.status == "ACTIVE"
    assert active_b.customer_id == "cust-customer_b"


def test_交接单按客户独立且双坐席互不抢占_AC_33() -> None:
    with (
        customer_client() as customer_a,
        customer_client() as customer_b,
        agent_client() as agent_a,
        agent_client() as agent_b,
    ):
        login_customer(customer_a, "customer_a")
        login_customer(customer_b, "customer_b")
        transfer(customer_a)
        transfer(customer_b)
        conversation_a = conversation_id_of(customer_a)
        conversation_b = conversation_id_of(customer_b)
        login_employee(agent_a, "agent_1")
        login_employee(agent_b, "agent_2")
        handoff_a = queue_item(agent_a, "customer_a")["handoff_id"]
        handoff_b = queue_item(agent_b, "customer_b")["handoff_id"]

        assert claim(agent_a, handoff_a)["conversation_id"] == conversation_a

        # 第二坐席：读甲会话 404，重复领取甲单 409，不产生副作用。
        assert agent_b.get(f"/workspace/conversations/{conversation_a}").status_code == 404
        conflict = agent_b.post(CLAIM.format(handoff_id=handoff_a))
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "CLAIM_CONFLICT"

        close_by_agent(agent_a, conversation_a)

        # 关闭甲单不影响乙单：乙仍在队列且可由 agent_2 领取。
        assert next(row for row in rows_of(ServiceHandoff) if row.id == handoff_b).status == QUEUED
        assert [item["handoff_id"] for item in queue(agent_b)] == [handoff_b]
        assert claim(agent_b, handoff_b)["conversation_id"] == conversation_b
        assert takeover(agent_b, conversation_b)["status"] == "HUMAN_ACTIVE"

    # 两张交接单归属各自会话与客户；甲单已关闭，乙单在人工中。
    first = next(row for row in rows_of(ServiceHandoff) if row.id == handoff_a)
    second = next(row for row in rows_of(ServiceHandoff) if row.id == handoff_b)
    assert first.conversation_id == conversation_a
    assert second.conversation_id == conversation_b
    assert first.customer_id == "cust-customer_a"
    assert second.customer_id == "cust-customer_b"
    assert first.journey_id != second.journey_id
    assert first.status == CLOSED
    assert second.status == "ACTIVE"
    assert conversation_of(conversation_a).status == CLOSED
    assert conversation_of(conversation_b).status == "HUMAN_ACTIVE"
