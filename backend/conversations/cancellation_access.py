"""取消归属闸门：客户本人，与坐席“本人接管 + 已核验订单”。

- 客户：订单归属由 OMS 网关按 `(tenant_id, oms_customer_id)` 判定，他人/不存在统一
  404；本模块只表达 actor 身份与确认权限。
- 坐席：必须同时满足同租户、会话由本人接管且处于 `HUMAN_ACTIVE`、交接单 `ACTIVE`、
  订单在交接单 `context["orders"]` 的已核验清单内。任一不满足返回 None，对外 404，
  不区分“不存在”与“无权”，避免泄露订单/任务存在性。
- 确认只接受客户 actor：`ensure_confirmation_allowed` 对非客户 actor 抛
  `CancellationForbidden`。F-33 没有坐席确认入口，HTTP 403 由 F-36 的工作台
  路由映射（AC-69）；客户确认入口本身按客户会话 + 任务归属鉴权。
- F-36 的工作台发起路由接入本模块；F-33 按执行卡 §2.3 的 S-2 seam 直接驱动。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.statuses import HANDOFF_ACTIVE, HUMAN_ACTIVE
from backend.identity.customer_sessions import Customer
from backend.identity.employee_sessions import Employee
from backend.platform.models import ServiceConversation, ServiceHandoff


class CancellationActorKind(StrEnum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"


class CancellationForbidden(Exception):
    """角色不具备该取消动作权限；由 F-36 工作台路由映射 403。"""


@dataclass(frozen=True)
class CancellationScope:
    """一次取消动作的授权上下文；只表达“谁、在哪个租户、哪些订单”。"""

    actor_kind: CancellationActorKind
    tenant_id: str
    owner_customer_id: str
    actor_id: str
    verified_order_ids: frozenset[str] = frozenset()


def customer_cancellation_scope(customer: Customer) -> CancellationScope:
    """客户本人：订单归属仍由网关按 OMS 客户身份判定。"""
    return CancellationScope(
        actor_kind=CancellationActorKind.CUSTOMER,
        tenant_id=customer.tenant_id,
        owner_customer_id=customer.id,
        actor_id=customer.id,
    )


def _verified_order_ids(context: Any) -> frozenset[str]:
    """从交接单快照里取已核验订单号；坏数据按“未核验”处理。"""
    if not isinstance(context, dict):
        return frozenset()
    orders = context.get("orders")
    if not isinstance(orders, list):
        return frozenset()
    return frozenset(
        str(item["order_id"]) for item in orders if isinstance(item, dict) and item.get("order_id")
    )


async def agent_cancellation_scope(
    db: AsyncSession,
    employee: Employee,
    conversation_id: str,
    order_id: str,
) -> CancellationScope | None:
    """坐席发起取消的授权上下文；任一条件不满足返回 None（对外 404）。"""
    conversation = (
        await db.execute(
            select(ServiceConversation).where(
                ServiceConversation.id == conversation_id,
                ServiceConversation.tenant_id == employee.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        return None
    if conversation.status != HUMAN_ACTIVE:
        return None
    if conversation.assigned_employee_id != employee.id:
        return None

    handoff = (
        await db.execute(
            select(ServiceHandoff).where(
                ServiceHandoff.tenant_id == employee.tenant_id,
                ServiceHandoff.conversation_id == conversation_id,
                ServiceHandoff.status == HANDOFF_ACTIVE,
            )
        )
    ).scalar_one_or_none()
    if handoff is None:
        return None

    verified = _verified_order_ids(handoff.context)
    if order_id not in verified:
        return None
    return CancellationScope(
        actor_kind=CancellationActorKind.AGENT,
        tenant_id=employee.tenant_id,
        owner_customer_id=conversation.customer_id,
        actor_id=employee.id,
        verified_order_ids=verified,
    )


def ensure_confirmation_allowed(scope: CancellationScope) -> None:
    """确认/拒绝只属于客户本人；调用方必须传入真实 actor 的 scope。

    客户确认入口的调用方只有客户会话，scope 恒为 CUSTOMER；坐席没有确认入口，
    代确认 403 由 F-36 的工作台路由在调用本函数后映射（AC-69）。
    """
    if scope.actor_kind is not CancellationActorKind.CUSTOMER:
        raise CancellationForbidden("确认只接受客户本人")
