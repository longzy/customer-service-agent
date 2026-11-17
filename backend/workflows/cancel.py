"""Cancellation Workflow：状态机、确认、幂等提交、恢复重试与惰性超时。"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.cancellation import CancellationState, OmsCancelState
from backend.identity import Identity
from backend.platform.models import CancellationRequest as CancellationRow
from backend.tools.gateway import GatewayError, ToolGateway

logger = logging.getLogger(__name__)

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


class TaskConflict(Exception):
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
    conversation_id: str | None = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    last_error_code: str | None = None
    oms_request_id: str | None = None
    version: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


class CancellationRepository(Protocol):
    async def create(self, task: CancellationTask) -> None: ...

    async def get(self, task_id: str, identity: Identity) -> CancellationTask: ...

    async def save(self, task: CancellationTask) -> None: ...

    async def list_recoverable(self) -> list[CancellationTask]: ...

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
                trace_id=task.trace_id,
                idempotency_key=task.idempotency_key,
                reason_code=task.reason_code,
                conversation_id=task.conversation_id,
                last_error_code=task.last_error_code,
                oms_request_id=task.oms_request_id,
                version=task.version,
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
            conversation_id=row.conversation_id,
            trace_id=row.trace_id,
            last_error_code=row.last_error_code,
            oms_request_id=row.oms_request_id,
            version=row.version,
        )

    async def list_recoverable(self) -> list[CancellationTask]:
        result = await self._session.execute(
            select(CancellationRow).where(
                CancellationRow.state.in_([state.value for state in RECOVERABLE_STATES])
            )
        )
        return [
            CancellationTask(
                id=row.id,
                tenant_id=row.tenant_id,
                user_id=row.user_id,
                order_id=row.order_id,
                state=CancellationState(row.state),
                idempotency_key=row.idempotency_key,
                expires_at=row.expires_at,
                reason_code=row.reason_code,
                conversation_id=row.conversation_id,
                trace_id=row.trace_id,
                last_error_code=row.last_error_code,
                oms_request_id=row.oms_request_id,
                version=row.version,
            )
            for row in result.scalars()
        ]

    async def save(self, task: CancellationTask) -> None:
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(CancellationRow)
                .where(
                    CancellationRow.id == task.id,
                    CancellationRow.version == task.version,
                )
                .values(
                    state=task.state.value,
                    reason_code=task.reason_code,
                    last_error_code=task.last_error_code,
                    oms_request_id=task.oms_request_id,
                    version=task.version + 1,
                )
            ),
        )
        if result.rowcount != 1:
            raise TaskConflict(task.id)
        task.version += 1

    async def commit(self) -> None:
        await self._session.commit()


class CancellationWorkflow:
    def __init__(
        self,
        repository: CancellationRepository,
        gateway: ToolGateway,
        confirm_timeout_minutes: int = 30,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        now: Callable[[], datetime] | None = None,
        audit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        confirmation: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._confirm_timeout = timedelta(minutes=confirm_timeout_minutes)
        self._max_retries = max_retries
        self._backoff = retry_backoff_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._audit = audit
        self._confirmation = confirmation

    async def _record(
        self,
        identity: Identity,
        task: CancellationTask,
        from_state: CancellationState,
        to_state: CancellationState,
        *,
        reason_code: str | None = None,
        result_status: str = "committed",
    ) -> None:
        if self._audit is None:
            return
        await self._audit(
            {
                "trace_id": task.trace_id,
                "identity": identity,
                "task_id": task.id,
                "order_id": task.order_id,
                "from_state": from_state.value,
                "to_state": to_state.value,
                "reason_code": reason_code,
                "result_status": result_status,
                "idempotency_key": task.idempotency_key,
            }
        )

    async def _confirm(
        self,
        identity: Identity,
        task: CancellationTask,
        action: str,
        result_status: str,
    ) -> None:
        if self._confirmation is None:
            return
        await self._confirmation(
            {
                "trace_id": task.trace_id,
                "identity": identity,
                "task_id": task.id,
                "order_id": task.order_id,
                "action": action,
                "result_status": result_status,
                "idempotency_key": task.idempotency_key,
            }
        )

    async def _invoke(
        self, name: str, payload: dict[str, Any], identity: Identity, trace_id: str
    ) -> Any:
        def call() -> Any:
            return self._gateway.invoke(name, payload, identity, trace_id)

        return await asyncio.to_thread(call)

    async def request(
        self,
        identity: Identity,
        order_id: str,
        trace_id: str,
        conversation_id: str | None = None,
    ) -> CancellationTask:
        eligibility = await self._invoke(
            "get_cancel_eligibility", {"order_id": order_id}, identity, trace_id
        )
        task = CancellationTask(
            id=str(uuid4()),
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            order_id=order_id,
            state=CancellationState.COLLECTING,
            conversation_id=conversation_id,
            trace_id=trace_id,
            idempotency_key=str(uuid4()),
            expires_at=self._now() + self._confirm_timeout,
        )
        await self._repository.create(task)
        if not eligibility["eligible"]:
            target = CancellationState.ELIGIBILITY_REJECTED
            task.reason_code = eligibility["reason_code"]
        else:
            target = CancellationState.AWAITING_CONFIRMATION
        await self._record(identity, task, task.state, target, reason_code=task.reason_code)
        task.state = target
        await self._repository.save(task)
        await self._repository.commit()
        return task

    async def confirm(
        self, identity: Identity, task_id: str, trace_id: str | None = None
    ) -> CancellationTask:
        task = await self._repository.get(task_id, identity)
        trace_id = task.trace_id
        if task.state in FINAL_STATES:
            await self._confirm(identity, task, "confirm", "idempotent")
            return task
        if task.state in RECOVERABLE_STATES:
            await self._confirm(identity, task, "confirm", "idempotent")
            return await self._recover(identity, task, trace_id)
        if task.state != CancellationState.AWAITING_CONFIRMATION:
            raise InvalidTransition(task.state.value)
        if self._expired(task):
            await self._confirm(identity, task, "confirm", "abandoned")
            await self._record(identity, task, task.state, CancellationState.ABANDONED)
            task.state = CancellationState.ABANDONED
            await self._repository.save(task)
            await self._repository.commit()
            return task

        await self._confirm(identity, task, "confirm", "committed")
        await self._record(
            identity, task, CancellationState.AWAITING_CONFIRMATION, CancellationState.SUBMITTING
        )
        task.state = CancellationState.SUBMITTING
        await self._repository.save(task)
        await self._repository.commit()

        try:
            body = await self._invoke(
                "submit_cancel",
                {"order_id": task.order_id, "idempotency_key": task.idempotency_key},
                identity,
                trace_id,
            )
            if body.get("state") == OmsCancelState.ACCEPTED.value:
                await self._finish(task, CancellationState.ACCEPTED)
                return await self._refresh_accepted(identity, task, trace_id)
            return await self._recover(identity, task, trace_id)
        except GatewayError as error:
            code = error.payload.get("code")
            if code == "OMS_REJECTED":
                return await self._finish(task, CancellationState.REJECTED)
            if code == "NOT_FOUND_OR_UNAUTHORIZED":
                return await self._finish(task, CancellationState.REJECTED)
            await self._record(identity, task, task.state, CancellationState.SUBMIT_UNKNOWN)
            task.state = CancellationState.SUBMIT_UNKNOWN
            task.last_error_code = str(code)
            await self._repository.save(task)
            await self._repository.commit()
            return await self._recover(identity, task, trace_id)

    async def recover_pending(self, trace_id: str | None = None) -> int:
        """启动恢复：扫描悬挂任务并按幂等键查询结果；优先使用任务自己的 trace。"""
        tasks = await self._repository.list_recoverable()
        recovered = 0
        for task in tasks:
            task_trace = task.trace_id
            identity = Identity(
                account_id="startup-recovery",
                user_id=task.user_id,
                tenant_id=task.tenant_id,
                display_name="",
                tenant_name="",
            )
            try:
                await self._recover(identity, task, task_trace)
            except TaskConflict:
                logger.warning("启动恢复遇到并发更新，跳过任务 %s", task.id)
                continue
            recovered += 1
        return recovered

    async def abandon(self, identity: Identity, task_id: str) -> CancellationTask:
        task = await self._repository.get(task_id, identity)
        if task.state in ACTIVE_STATES:
            await self._confirm(identity, task, "abandon", "abandoned")
            await self._record(identity, task, task.state, CancellationState.ABANDONED)
            task.state = CancellationState.ABANDONED
            await self._repository.save(task)
            await self._repository.commit()
        else:
            await self._confirm(identity, task, "abandon", "idempotent")
        return task

    async def get(
        self, identity: Identity, task_id: str, trace_id: str | None = None
    ) -> CancellationTask:
        task = await self._repository.get(task_id, identity)
        trace_id = task.trace_id
        if task.state in ACTIVE_STATES and self._expired(task):
            await self._record(identity, task, task.state, CancellationState.ABANDONED)
            task.state = CancellationState.ABANDONED
            await self._repository.save(task)
            await self._repository.commit()
        elif task.state in RECOVERABLE_STATES:
            task = await self._recover(identity, task, trace_id)
        elif task.state == CancellationState.ACCEPTED:
            task = await self._refresh_accepted(identity, task, trace_id)
        return task

    async def _refresh_accepted(
        self, identity: Identity, task: CancellationTask, trace_id: str
    ) -> CancellationTask:
        """已受理后只允许推进到 CANCELLED；查询失败保持 ACCEPTED，不降级。"""
        trace_id = task.trace_id
        try:
            body = await self._invoke(
                "get_cancel_result",
                {"idempotency_key": task.idempotency_key},
                identity,
                trace_id,
            )
        except GatewayError:
            return task
        if body.get("state") == OmsCancelState.CANCELLED.value:
            return await self._finish(task, CancellationState.CANCELLED)
        return task

    async def _recover(
        self, identity: Identity, task: CancellationTask, trace_id: str
    ) -> CancellationTask:
        trace_id = task.trace_id
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
                task.last_error_code = code
                await self._repository.save(task)
                await self._repository.commit()
                if code in RETRYABLE_CODES:
                    await asyncio.sleep(self._backoff * (2**attempt))
                    continue
                break
            mapped = OMS_TO_STATE[OmsCancelState(body["state"])]
            if mapped == CancellationState.SUBMIT_UNKNOWN:
                await asyncio.sleep(self._backoff * (2**attempt))
                continue
            return await self._finish(task, mapped)
        return await self._finish(task, CancellationState.MANUAL_REVIEW)

    async def _finish(self, task: CancellationTask, state: CancellationState) -> CancellationTask:
        previous = task.state
        identity = Identity(
            account_id=task.user_id,
            user_id=task.user_id,
            tenant_id=task.tenant_id,
            display_name="",
            tenant_name="",
        )
        if previous is not state:
            await self._record(identity, task, previous, state)
        task.state = state
        await self._repository.save(task)
        await self._repository.commit()
        return task

    def _expired(self, task: CancellationTask) -> bool:
        return self._now() >= task.expires_at
