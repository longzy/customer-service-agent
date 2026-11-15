"""意图类型：模型 schema 与分类逻辑的单一来源。"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Intent(StrEnum):
    QUERY_ORDER = "QUERY_ORDER"
    QUERY_RECENT = "QUERY_RECENT"
    CANCEL_ORDER = "CANCEL_ORDER"
    CONFIRM_CANCEL = "CONFIRM_CANCEL"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    UNKNOWN = "UNKNOWN"


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    order_id: str | None = None
    candidate_order_ids: list[str] = []
    needs_clarification: bool = False
