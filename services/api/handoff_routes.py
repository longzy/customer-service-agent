"""人工转接接口。"""

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth import Identity, current_identity
from services.api.db import get_session
from services.api.handoff import create_handoff

router = APIRouter()


class HandoffPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None


@router.post("/handoff", status_code=201)
async def create(
    payload: HandoffPayload,
    identity: Annotated[Identity, Depends(current_identity)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    try:
        handoff = await create_handoff(session, identity, payload.conversation_id, str(uuid4()))
    except LookupError as error:
        raise HTTPException(status_code=404, detail="会话不存在") from error
    return {
        "id": handoff.id,
        "conversation_id": handoff.conversation_id,
        "summary": handoff.summary,
        "context": handoff.context,
        "trace_id": handoff.trace_id,
    }
