"""Cancellation Workflow：状态机、确认、幂等提交、恢复重试与惰性超时。"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth import Identity
from services.api.domain.cancellation import CancellationState, OmsCancelState
from services.api.models import CancellationRequest as CancellationRow
from services.tools.gateway import GatewayError, ToolGateway

ACTIVE_STATES = {CancellationState.COLLECTING, CancellationState.AWAITING_CONFIRMATION}
RECOVERABLE_STATES = {CancellationState.SUBMITTING, CancellationState.SUBMIT_UNKNOWN}
FINAL_STATES = {
    CancellationState.ACCEPTED,
    CancellationState.CANCELLED,
    CancellationState.REJECTED,
    CancellationState.MANUAL_REVIEW,
    CancellationState.ABANDONED,
    CancellationState.ELIGIBILITY_REJECTED,
}
RETRYABLE_CODES = {
    "DEPENDENCY_TIMEOUT",
    "DEPENDENCY_UNAVAILABLE",
    "INVALID_RESPONSE",
    "NOT_FOUND_OR_UNAUTHORIZED",
}
OMS_TO_STATE = {
    OmsCancelState.ACCEPTED: CancellationState.ACCEPTED,
    OmsCancelState.CANCELLED: CancellationState.CANCELLED,
    OmsCancelState.REJECTED: CancellationState.REJECTED,
    OmsCancelState.UNKNOWN: CancellationState.SUBMIT_UNKNOWN,
}


class TaskNotFound(Exception):
    pass


class InvalidTransition(Exception):
    pass


@dataclass
class CancellationTask:
    id: str
    tenant_id: str
    user_id: str
    order_id: str
    state: CancellationState
    idempotency_key: str
    expires_at: datetime
    reason_code: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class CancellationRepository(Protocol):
    async def create(self, task: CancellationTask) -> None: ...

    async def get(self, task_id: str, identity: Identity) -> CancellationTask: ...

    async def save(self, task: CancellationTask) -> None: ...

    async def commit(self) -> None: ...


class SqlCancellationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, task: CancellationTask) -> None:
        self._session.add(
            CancellationRow(
                id=task.id,
                tenant_id=task.tenant_id,
                user_id=task.user_id,
                order_id=task.order_id,
                state=task.state.value,
                idempotency_key=task.idempotency_key,
                reason_code=task.reason_code,
                expires_at=task.expires_at,
            )
        )

    async def get(self, task_id: str, identity: Identity) -> CancellationTask:
        result = await self._session.execute(
            select(CancellationRow).where(
                CancellationRow.id == task_id,
                CancellationRow.tenant_id == identity.tenant_id,
                CancellationRow.user_id == identity.user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise TaskNotFound(task_id)
        return CancellationTask(
            id=row.id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            order_id=row.order_id,
            state=CancellationState(row.state),
            idempotency_key=row.idempotency_key,
            expires_at=row.expires_at,
            reason_code=row.reason_code,
        )

    async def save(self, task: CancellationTask) -> None:
        row = await self._session.get(CancellationRow, task.id)
        if row is None:
            raise TaskNotFound(task.id)
        row.state = task.state.value
        row.reason_code = task.reason_code

    async def commit(self) -> None:
        await self._session.commit()


class CancellationWorkflow:
    def __init__(
        self,
        repository: CancellationRepository,
        gateway: ToolGateway,
        confirm_timeout_minutes: int = 30,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.2,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._confirm_timeout = timedelta(minutes=confirm_timeout_minutes)
        self._max_retries = max_retries
        self._backoff = retry_backoff_seconds
        self._now = now or (lambda: datetime.now(UTC))

    async def _invoke(
        self, name: str, payload: dict[str, Any], identity: Identity, trace_id: str
    ) -> Any:
        def call() -> Any:
            return self._gateway.invoke(name, payload, identity, trace_id)

        return await asyncio.to_thread(call)

    async def request(self, identity: Identity, order_id: str, trace_id: str) -> CancellationTask:
        eligibility = await self._invoke(
            "get_cancel_eligibility", {"order_id": order_id}, identity, trace_id
        )
        task = CancellationTask(
            id=str(uuid4()),
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            order_id=order_id,
            state=CancellationState.AWAITING_CONFIRMATION,
            idempotency_key=str(uuid4()),
            expires_at=self._now() + self._confirm_timeout,
        )
        if not eligibility["eligible"]:
            task.state = CancellationState.ELIGIBILITY_REJECTED
            task.reason_code = eligibility["reason_code"]
        await self._repository.create(task)
        await self._repository.commit()
        return task

    async def confirm(self, identity: Identity, task_id: str, trace_id: str) -> CancellationTask:
        task = await self._repository.get(task_id, identity)
        if task.state in FINAL_STATES:
            return task
        if task.state in RECOVERABLE_STATES:
            return await self._recover(identity, task, trace_id)
        if task.state != CancellationState.AWAITING_CONFIRMATION:
            raise InvalidTransition(task.state.value)
        if self._expired(task):
            task.state = CancellationState.ABANDONED
            await self._repository.save(task)
            await self._repository.commit()
            return task

        task.state = CancellationState.SUBMITTING
        await self._repository.save(task)
        await self._repository.commit()

        try:
            await self._invoke(
                "submit_cancel",
                {"order_id": task.order_id, "idempotency_key": task.idempotency_key},
                identity,
                trace_id,
            )
        except GatewayError as error:
            code = error.payload.get("code")
            if code == "OMS_REJECTED":
                return await self._finish(task, CancellationState.REJECTED)
            if code == "NOT_FOUND_OR_UNAUTHORIZED":
                return await self._finish(task, CancellationState.REJECTED)
            task.state = CancellationState.SUBMIT_UNKNOWN
            await self._repository.save(task)
            await self._repository.commit()
            return await self._recover(identity, task, trace_id)

        return await self._recover(identity, task, trace_id)

    async def abandon(self, identity: Identity, task_id: str) -> CancellationTask:
        task = await self._repository.get(task_id, identity)
        if task.state in ACTIVE_STATES:
            task.state = CancellationState.ABANDONED
            await self._repository.save(task)
            await self._repository.commit()
        return task

    async def get(self, identity: Identity, task_id: str, trace_id: str) -> CancellationTask:
        task = await self._repository.get(task_id, identity)
        if task.state in ACTIVE_STATES and self._expired(task):
            task.state = CancellationState.ABANDONED
            await self._repository.save(task)
            await self._repository.commit()
        elif task.state in RECOVERABLE_STATES:
            task = await self._recover(identity, task, trace_id)
        return task

    async def _recover(
        self, identity: Identity, task: CancellationTask, trace_id: str
    ) -> CancellationTask:
        for attempt in range(self._max_retries):
            try:
                body = await self._invoke(
                    "get_cancel_result",
                    {"idempotency_key": task.idempotency_key},
                    identity,
                    trace_id,
                )
            except GatewayError as error:
                code = str(error.payload.get("code"))
                if code in RETRYABLE_CODES:
                    await asyncio.sleep(self._backoff * (2**attempt))
                    continue
                break
            mapped = OMS_TO_STATE[OmsCancelState(body["state"])]
            return await self._finish(task, mapped)
        return await self._finish(task, CancellationState.MANUAL_REVIEW)

    async def _finish(self, task: CancellationTask, state: CancellationState) -> CancellationTask:
        task.state = state
        await self._repository.save(task)
        await self._repository.commit()
        return task

    def _expired(self, task: CancellationTask) -> bool:
        return self._now() >= task.expires_at
