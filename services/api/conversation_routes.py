"""Conversation API：接收消息、编排回复并落库。"""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent_runtime.chat import ConversationRepository, ConversationService
from services.agent_runtime.intent import IntentError
from services.agent_runtime.model import ModelError
from services.api.auth import Identity, current_identity
from services.api.db import get_session
from services.api.handoff import create_handoff
from services.api.models import Conversation, Handoff, Message
from services.api.settings import settings
from services.workflows.cancel import CancellationWorkflow, SqlCancellationRepository

router = APIRouter()


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)
    conversation_id: str | None = None


class SqlConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, identity: Identity, conversation_id: str | None) -> str:
        if conversation_id:
            result = await self._session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == identity.tenant_id,
                    Conversation.user_id == identity.user_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise PermissionError("会话不存在或不属于当前用户")
            return existing.id
        from uuid import uuid4

        conversation = Conversation(
            id=str(uuid4()), tenant_id=identity.tenant_id, user_id=identity.user_id
        )
        self._session.add(conversation)
        return conversation.id

    async def add_message(
        self, conversation_id: str, role: str, content: str, trace_id: str
    ) -> None:
        from uuid import uuid4

        self._session.add(
            Message(
                id=str(uuid4()),
                conversation_id=conversation_id,
                role=role,
                content=content,
                trace_id=trace_id,
            )
        )

    async def commit(self) -> None:
        await self._session.commit()


def get_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConversationRepository:
    return SqlConversationRepository(session)


@router.post("/message")
async def send_message(
    payload: MessageRequest,
    request: Request,
    identity: Annotated[Identity, Depends(current_identity)],
    repository: Annotated[ConversationRepository, Depends(get_repository)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    if payload.conversation_id:
        handed = await session.scalar(
            select(Handoff.id).where(
                Handoff.conversation_id == payload.conversation_id,
                Handoff.tenant_id == identity.tenant_id,
                Handoff.user_id == identity.user_id,
            )
        )
        if handed:
            raise HTTPException(status_code=409, detail="已转人工，自动回复已停止")
    workflow = CancellationWorkflow(
        SqlCancellationRepository(session),
        request.app.state.cancel_gateway,
        confirm_timeout_minutes=settings.confirm_timeout_minutes,
    )

    async def on_handoff(conversation_id: str, trace_id: str) -> None:
        await create_handoff(session, identity, conversation_id, trace_id)

    service = ConversationService(
        repository,
        request.app.state.model_client,
        request.app.state.query_gateway,
        cancellation=workflow,
        handoff=on_handoff,
    )
    try:
        reply = await service.handle(identity, payload.content, payload.conversation_id)
    except PermissionError as error:
        raise HTTPException(status_code=404, detail="会话不存在") from error
    except (ModelError, IntentError) as error:
        # 用户消息已在编排开始前提交，这里再提交一次兜底
        await repository.commit()
        raise HTTPException(status_code=503, detail="模型服务不可用") from error
    await repository.commit()
    return asdict(reply)
