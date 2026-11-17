"""坐席读取会话的归属门禁。

- 只允许读取同租户且 `assigned_employee_id` 为本人的会话。
- 未领取、他人、跨租户与不存在统一返回 None，由 API 层转 404。
- 本模块只读，不提交事务。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.platform.models import ServiceConversation


@dataclass(frozen=True)
class WorkspaceConversation:
    id: str
    status: str


async def get_assigned_conversation(
    db: AsyncSession,
    tenant_id: str,
    employee_id: str,
    conversation_id: str,
) -> WorkspaceConversation | None:
    statement = select(ServiceConversation).where(
        ServiceConversation.id == conversation_id,
        ServiceConversation.tenant_id == tenant_id,
        ServiceConversation.assigned_employee_id == employee_id,
    )
    row = (await db.execute(statement)).scalar_one_or_none()
    if row is None:
        return None
    return WorkspaceConversation(id=row.id, status=row.status)
