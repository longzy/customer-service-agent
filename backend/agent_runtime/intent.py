"""意图分类与订单澄清判定。"""

import re

from pydantic import ValidationError

from backend.agent_runtime.model import ModelClient
from backend.agent_runtime.types import Classification, Intent

ORDER_PATTERN = re.compile(r"(?<![A-Za-z0-9-])ORD-\d{4,12}(?![\d-])", re.IGNORECASE)


class IntentError(Exception):
    """模型输出不符合意图契约。"""


async def classify_message(message: str, client: ModelClient) -> Classification:
    raw = await client.classify(message)
    try:
        base = Classification.model_validate(raw)
    except ValidationError as error:
        raise IntentError(str(error)) from error

    mentioned = [item.upper() for item in ORDER_PATTERN.findall(message)]
    candidates = list(dict.fromkeys(mentioned))

    model_order = base.order_id.upper() if base.order_id else None
    if model_order is not None:
        if candidates and model_order not in candidates:
            # 模型幻觉或注入：以用户消息中的订单号为准
            model_order = None
        elif not candidates:
            raise IntentError("模型返回了消息中不存在的订单号")

    if len(candidates) > 1:
        order_id: str | None = None
        needs_clarification = True
    else:
        order_id = model_order or (candidates[0] if candidates else None)
        needs_clarification = base.intent == Intent.CANCEL_ORDER and order_id is None

    return Classification(
        intent=base.intent,
        order_id=order_id,
        candidate_order_ids=candidates if len(candidates) > 1 else [],
        needs_clarification=needs_clarification,
    )
