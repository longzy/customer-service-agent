"""取消任务接口：创建、确认与查询。"""

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth import Identity, current_identity
from services.api.db import get_session
from services.api.domain.cancellation import render_result
from services.api.settings import settings
from services.tools.gateway import GatewayError
from services.workflows.cancel import (
    CancellationRepository,
    CancellationTask,
    CancellationWorkflow,
    InvalidTransition,
    SqlCancellationRepository,
    TaskConflict,
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
    copy = render_result(task.state, task.reason_code)
    return {
        "id": task.id,
        "order_id": task.order_id,
        "state": task.state.value,
        "state_text": copy.state_text,
        "reason_text": copy.reason_text,
        "next_step": copy.next_step,
        "reason_code": task.reason_code,
        "expires_at": task.expires_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("")
async def create_request(
    payload: RequestPayload,
    identity: Annotated[Identity, Depends(current_identity)],
    workflow: Annotated[CancellationWorkflow, Depends(_workflow)],
) -> Any:
    try:
        task = await workflow.request(identity, payload.order_id, str(uuid4()))
    except GatewayError as error:
        return JSONResponse(status_code=error.status_code, content=error.payload)
    except TaskConflict as error:
        raise HTTPException(status_code=409, detail="任务已被其他请求更新") from error
    return _public(task)


@router.post("/{task_id}/confirm")
async def confirm_request(
    task_id: str,
    identity: Annotated[Identity, Depends(current_identity)],
    workflow: Annotated[CancellationWorkflow, Depends(_workflow)],
) -> Any:
    try:
        task = await workflow.confirm(identity, task_id, str(uuid4()))
    except GatewayError as error:
        return JSONResponse(status_code=error.status_code, content=error.payload)
    except TaskNotFound as error:
        raise HTTPException(status_code=404, detail="任务不存在") from error
    except InvalidTransition as error:
        raise HTTPException(status_code=409, detail="任务状态不允许确认") from error
    except TaskConflict as error:
        raise HTTPException(status_code=409, detail="任务已被其他请求更新") from error
    return _public(task)


@router.get("/{task_id}")
async def get_request(
    task_id: str,
    identity: Annotated[Identity, Depends(current_identity)],
    workflow: Annotated[CancellationWorkflow, Depends(_workflow)],
) -> dict[str, Any]:
    try:
        task = await workflow.get(identity, task_id, str(uuid4()))
    except TaskNotFound as error:
        raise HTTPException(status_code=404, detail="任务不存在") from error
    except TaskConflict as error:
        raise HTTPException(status_code=409, detail="任务已被其他请求更新") from error
    return _public(task)


@router.post("/{task_id}/abandon")
async def abandon_request(
    task_id: str,
    identity: Annotated[Identity, Depends(current_identity)],
    workflow: Annotated[CancellationWorkflow, Depends(_workflow)],
) -> dict[str, Any]:
    try:
        task = await workflow.abandon(identity, task_id)
    except TaskNotFound as error:
        raise HTTPException(status_code=404, detail="任务不存在") from error
    except TaskConflict as error:
        raise HTTPException(status_code=409, detail="任务已被其他请求更新") from error
    return _public(task)
