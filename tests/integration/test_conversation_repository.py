"""真实 SQL 仓储：归属、持久化与 trace（AC-01、AC-17 的字段）。"""

import pytest
from sqlalchemy import delete, func, select

from backend.api.conversation_routes import SqlConversationRepository
from backend.identity import Identity
from backend.platform.db import session_factory
from backend.platform.models import Conversation, Message
from tests.integration.db_utils import db_available

pytestmark = pytest.mark.skipif(not db_available(), reason="Postgres 不可用")

OWNER = Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A")
SAME_TENANT = Identity("li-hua", "user-a2", "tenant-a", "李华", "示例商户 A")
OTHER_TENANT = Identity("wang-qiang", "user-b1", "tenant-b", "王强", "示例商户 B")


async def test_仓储持久化与归属隔离_AC_01() -> None:
    async with session_factory() as session:
        repo = SqlConversationRepository(session)
        conversation_id = await repo.get_or_create(OWNER, None)
        await repo.add_message(conversation_id, "user", "查 ORD-10001", "trace-1")
        await repo.add_message(conversation_id, "assistant", "订单 ORD-10001", "trace-1")
        await repo.commit()

        rows = (
            await session.execute(
                select(Message.role, Message.content, Message.trace_id).where(
                    Message.conversation_id == conversation_id
                )
            )
        ).all()
        assert [row[0] for row in rows] == ["user", "assistant"]
        assert {row[2] for row in rows} == {"trace-1"}

        with pytest.raises(PermissionError):
            await repo.get_or_create(SAME_TENANT, conversation_id)
        with pytest.raises(PermissionError):
            await repo.get_or_create(OTHER_TENANT, conversation_id)

        await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
        await session.commit()
        remaining = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        assert remaining == 0, "删除会话应级联删除消息"
