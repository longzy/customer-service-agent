"""意图分类与订单澄清判定。"""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError

from services.agent_runtime.model import ModelClient

ORDER_PATTERN = re.compile(r"ORD-\d{4,}")


class Intent(StrEnum):
    QUERY_ORDER = "QUERY_ORDER"
    QUERY_RECENT = "QUERY_RECENT"
    CANCEL_ORDER = "CANCEL_ORDER"
    CONFIRM_CANCEL = "CONFIRM_CANCEL"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"
    UNKNOWN = "UNKNOWN"


class IntentError(Exception):
    """模型输出不符合意图契约。"""


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    order_id: str | None = None
    candidate_order_ids: list[str] = []
    needs_clarification: bool = False


async def classify_message(message: str, client: ModelClient) -> Classification:
    raw = await client.classify(message)
    try:
        base = Classification.model_validate(raw)
    except ValidationError as error:
        raise IntentError(str(error)) from error

    mentioned = ORDER_PATTERN.findall(message)
    candidates = list(dict.fromkeys(mentioned))
    order_id = base.order_id or (candidates[0] if len(candidates) == 1 else None)
    needs_clarification = len(candidates) > 1 or (
        base.intent == Intent.CANCEL_ORDER and order_id is None
    )
    return Classification(
        intent=base.intent,
        order_id=order_id,
        candidate_order_ids=candidates if len(candidates) > 1 else [],
        needs_clarification=needs_clarification,
    )
