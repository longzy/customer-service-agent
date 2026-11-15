"""取消任务接口：创建、确认与查询。"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth import Identity, current_identity
from services.api.db import get_session
from services.api.settings import settings
from services.workflows.cancel import (
    CancellationRepository,
    CancellationTask,
    CancellationWorkflow,
    InvalidTransition,
    SqlCancellationRepository,
    TaskNotFound,
)

router = APIRouter(prefix="/cancellation-requests")


class RequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str


def get_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CancellationRepository:
    return SqlCancellationRepository(session)


def _workflow(
    request: Request, repository: Annotated[CancellationRepository, Depends(get_repository)]
) -> CancellationWorkflow:
    return CancellationWorkflow(
        repository,
        request.app.state.cancel_gateway,
        confirm_timeout_minutes=settings.confirm_timeout_minutes,
    )


def _public(task: CancellationTask) -> dict[str, Any]:
    """只暴露前端需要的字段；幂等键与身份信息不出接口。"""
    return {
        "id": task.id,
        "order_id": task.order_id,
        "state": task.state.value,
        "reason_code": task.reason_code,
        "expires_at": task.expires_at.isoformat(),
    }


@router.post("")
async def create_request(
    payload: RequestPayload,
    identity: Annotated[Identity, Depends(current_identity)],
    workflow: Annotated[CancellationWorkflow, Depends(_workflow)],
) -> dict[str, Any]:
    task = await workflow.request(identity, payload.order_id, str(identity.user_id))
    return _public(task)


@router.post("/{task_id}/confirm")
async def confirm_request(
    task_id: str,
    identity: Annotated[Identity, Depends(current_identity)],
    workflow: Annotated[CancellationWorkflow, Depends(_workflow)],
) -> dict[str, Any]:
    try:
        task = await workflow.confirm(identity, task_id, str(identity.user_id))
    except TaskNotFound as error:
        raise HTTPException(status_code=404, detail="任务不存在") from error
    except InvalidTransition as error:
        raise HTTPException(status_code=409, detail="任务状态不允许确认") from error
    return _public(task)


@router.get("/{task_id}")
async def get_request(
    task_id: str,
    identity: Annotated[Identity, Depends(current_identity)],
    workflow: Annotated[CancellationWorkflow, Depends(_workflow)],
) -> dict[str, Any]:
    try:
        task = await workflow.get(identity, task_id)
    except TaskNotFound as error:
        raise HTTPException(status_code=404, detail="任务不存在") from error
    return _public(task)
