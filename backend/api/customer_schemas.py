"""客户 API 的响应契约：OpenAPI 与前端类型的唯一来源。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ConversationStatus = Literal[
    "AI_ACTIVE",
    "QUEUED",
    "CLAIMED",
    "HUMAN_ACTIVE",
    "CLOSED",
]
MessageAuthor = Literal["customer", "ai", "agent", "system"]


class ErrorEnvelope(BaseModel):
    """所有新 M1 API 的错误封套。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    retryable: bool
    visible: bool
    message: str


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


class MessagePublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    author_type: MessageAuthor
    content: str
    created_at: str


class MessagePageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    status: ConversationStatus
    after_id: int
    messages: list[MessagePublic]
