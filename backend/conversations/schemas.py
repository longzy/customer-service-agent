"""会话域的 HTTP 契约：客户会话、消息与工作台读模型。"""

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ConversationStatus = Literal[
    "AI_ACTIVE",
    "QUEUED",
    "CLAIMED",
    "HUMAN_ACTIVE",
    "CLOSED",
]
MessageAuthor = Literal["customer", "ai", "agent", "system"]


class CustomerLoginRequest(BaseModel):
    """只接受用户名/密码；租户与客户 id 只能来自服务端配置与 session。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _strip_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username 不能为空")
        return value


class CustomerMessageRequest(BaseModel):
    """客户消息；身份与会话只能来自服务端 session。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content 不能为空")
        return value


class CustomerPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    username: str
    display_name: str


class ConversationPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: ConversationStatus
    after_id: int


class CustomerSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: CustomerPublic
    conversation: ConversationPublic
    expires_at: str


class OrderSummaryPublic(BaseModel):
    """订单摘要快照（消息载荷与交接单共用）；只含白名单字段。"""

    model_config = ConfigDict(extra="forbid")

    order_id: str
    item_summary: str
    order_status: str
    status_label: str
    amount_cents: int = Field(ge=0)
    currency: str
    created_at: str
    created_at_local: str


class MessagePayload(BaseModel):
    """AI 订单消息的结构化快照；空列表表示查无/失败，前端不渲染卡片。"""

    model_config = ConfigDict(extra="forbid")

    orders: list[OrderSummaryPublic] = Field(default_factory=list, max_length=5)

    @classmethod
    def from_stored(cls, payload: Mapping[str, Any] | None) -> "MessagePayload | None":
        """读模型只投影 `orders`；坏元素丢弃，旧消息的非订单载荷不会被带到 API。"""
        if not isinstance(payload, Mapping):
            return None
        raw = payload.get("orders")
        if not isinstance(raw, list):
            return cls()
        orders: list[OrderSummaryPublic] = []
        for item in raw[:5]:
            if not isinstance(item, dict):
                continue
            try:
                orders.append(OrderSummaryPublic.model_validate(item))
            except ValidationError:
                # 落库快照由服务端构造；坏行只说明历史/手工数据，读模型降级不击穿页面。
                continue
        return cls(orders=orders)


class MessagePublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    author_type: MessageAuthor
    content: str
    created_at: str
    # AI 订单消息的结构化快照；客户/系统消息为 None。字段只含白名单摘要。
    payload: MessagePayload | None = None


class MessagePageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    status: ConversationStatus
    after_id: int
    messages: list[MessagePublic]


class WorkspaceCustomerPublic(BaseModel):
    """坐席可见的客户账号；不暴露客户内部 id 与联系方式。"""

    model_config = ConfigDict(extra="forbid")

    username: str
    display_name: str


class WorkspaceContextMessage(BaseModel):
    """交接单快照里的消息；正文在创建交接单时已脱敏。"""

    model_config = ConfigDict(extra="forbid")

    id: int
    author_type: MessageAuthor
    content: str
    created_at: str


class WorkspaceAiTraceEvent(BaseModel):
    """AI 轨迹只含事件元数据，不含 prompt/response 正文。"""

    model_config = ConfigDict(extra="forbid")

    event_type: str
    name: str
    status: str
    confidence: float | None
    created_at: str


class WorkspaceHandoffDetail(BaseModel):
    """完整交接单：摘要、原因、待办与创建时的上下文快照。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    reason: str
    summary: str
    pending_step: str | None
    order_count: int = Field(ge=0)
    # F-28：区分“有订单 / 暂无订单 / 订单信息不可用”，空列表不写空摘要。
    # 契约层保持独立字面量；取值与 `handoffs.OrderContextStatus` 一致。
    order_context_status: Literal["ok", "empty", "failed", "unknown"]
    orders: list[OrderSummaryPublic] = Field(default_factory=list, max_length=5)
    messages: list[WorkspaceContextMessage]
    ai_trace: list[WorkspaceAiTraceEvent]
    failure_count: int | None = Field(default=None, ge=2)
    last_error: str | None = None


class WorkspaceConversationResponse(BaseModel):
    """领取者可见的完整上下文；未领取/他人/跨租户由 API 返回 404。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: ConversationStatus
    customer: WorkspaceCustomerPublic
    handoff: WorkspaceHandoffDetail | None


class WorkspaceQueueItem(BaseModel):
    """队列摘要：领取前只暴露判断“接谁”所需的最小信息。"""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    conversation_id: str
    customer_username: str
    customer_display_name: str
    waiting_seconds: int = Field(ge=0)
    reason: str
    order_count: int = Field(ge=0)
    last_message: str


class WorkspaceQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WorkspaceQueueItem]


class WorkspaceClaimResponse(BaseModel):
    """领取成功后的最小回执；`status` 是同一事务里的会话状态。"""

    model_config = ConfigDict(extra="forbid")

    handoff_id: str
    conversation_id: str
    status: ConversationStatus


class WorkspaceTakeoverResponse(BaseModel):
    """接管成功后的最小回执；`status` 固定为 `HUMAN_ACTIVE`。"""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    status: ConversationStatus


class AgentMessageRequest(BaseModel):
    """坐席回复正文；身份与会话只能来自服务端 session 与路径。"""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content 不能为空")
        return value
