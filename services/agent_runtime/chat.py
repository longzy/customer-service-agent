"""一轮对话的编排：分类、工具调用、回复与持久化。"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from services.agent_runtime.intent import classify_message
from services.agent_runtime.types import Intent
from services.api.auth import Identity
from services.api.domain.errors import ErrorCode
from services.api.domain.orders import ORDER_STATUS_TEXT, OrderStatus
from services.tools.gateway import GatewayError, ToolGateway


class ConversationRepository(Protocol):
    async def get_or_create(self, identity: Identity, conversation_id: str | None) -> str: ...

    async def add_message(
        self, conversation_id: str, role: str, content: str, trace_id: str
    ) -> None: ...

    async def commit(self) -> None: ...


@dataclass
class Reply:
    conversation_id: str
    trace_id: str
    reply: str
    orders: list[dict[str, Any]] = field(default_factory=list)
    clarification: list[str] = field(default_factory=list)


def _gateway_reply(error: GatewayError) -> str:
    """只展示对用户可见的错误；内部错误不暴露未发生的动作。"""
    payload = error.payload
    if payload.get("code") == ErrorCode.NOT_FOUND_OR_UNAUTHORIZED.value:
        return "查无此单，或你没有权限查看该订单。"
    if payload.get("visible") is True:
        return str(payload.get("message", "操作未完成，请稍后再试。"))
    return "系统暂时不可用，请稍后再试。"


def _status_text(order: dict[str, Any]) -> str:
    return ORDER_STATUS_TEXT[OrderStatus(order["order_status"])]


def _summary_text(order: dict[str, Any]) -> str:
    status = _status_text(order)
    return (
        f"订单 {order['order_id']}：{order['item_summary']}，"
        f"状态 {status}，金额 {order['amount_cents'] / 100:.2f} 元。"
    )


class ConversationService:
    def __init__(
        self, repository: ConversationRepository, model: Any, gateway: ToolGateway
    ) -> None:
        self._repository = repository
        self._model = model
        self._gateway = gateway

    async def handle(
        self, identity: Identity, content: str, conversation_id: str | None = None
    ) -> Reply:
        conversation = await self._repository.get_or_create(identity, conversation_id)
        trace_id = str(uuid4())
        await self._repository.add_message(conversation, "user", content, trace_id)
        # 模型调用前先落用户消息，避免超时或失败时丢输入
        await self._repository.commit()

        classification = await classify_message(content, self._model)
        if classification.needs_clarification:
            reply = self._clarify(classification.candidate_order_ids)
            await self._repository.add_message(conversation, "assistant", reply, trace_id)
            return Reply(
                conversation_id=conversation,
                trace_id=trace_id,
                reply=reply,
                clarification=classification.candidate_order_ids,
            )

        orders: list[dict[str, Any]] = []
        try:
            if classification.intent == Intent.QUERY_ORDER and classification.order_id:
                single = await asyncio.to_thread(
                    self._gateway.invoke,
                    "get_order",
                    {"order_id": classification.order_id},
                    identity,
                    trace_id,
                )
                orders = [single]
            elif classification.intent == Intent.QUERY_RECENT:
                orders = await asyncio.to_thread(
                    self._gateway.invoke,
                    "list_recent_orders",
                    {"limit": 5},
                    identity,
                    trace_id,
                )
        except GatewayError as error:
            reply = _gateway_reply(error)
            await self._repository.add_message(conversation, "assistant", reply, trace_id)
            return Reply(conversation_id=conversation, trace_id=trace_id, reply=reply)

        if orders:
            reply = "\n".join(_summary_text(order) for order in orders)
        elif classification.intent == Intent.HUMAN_HANDOFF:
            reply = "已记录转人工请求，人工转接功能将在后续版本开放。"
        elif classification.intent in (Intent.CANCEL_ORDER, Intent.CONFIRM_CANCEL):
            reply = "取消功能将在后续版本开放，当前可以先查询订单。"
        else:
            reply = "我暂时没理解，请提供订单号，或说明要查询的订单。"

        await self._repository.add_message(conversation, "assistant", reply, trace_id)
        return Reply(
            conversation_id=conversation,
            trace_id=trace_id,
            reply=reply,
            orders=[{**order, "status_text": _status_text(order)} for order in orders],
        )

    @staticmethod
    def _clarify(candidates: list[str]) -> str:
        if candidates:
            return "你提到了多笔订单，请确认是哪一笔：" + "、".join(candidates)
        return "请提供要查询的订单号，例如 ORD-10001。"
