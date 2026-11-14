"""订单领域类型。M1 只把 PAID_UNFULFILLED 视为可取消。"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OrderStatus(StrEnum):
    PAID_UNFULFILLED = "PAID_UNFULFILLED"
    FULFILLING = "FULFILLING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


def is_cancelable(status: OrderStatus) -> bool:
    """M1 的取消资格只取决于订单状态；归属与租户由授权层负责。"""
    return status is OrderStatus.PAID_UNFULFILLED


class OrderSummary(BaseModel):
    """订单摘要。金额只用整数分，时间统一归一为 UTC。"""

    order_id: str = Field(min_length=1)
    item_summary: str = Field(min_length=1)
    order_status: OrderStatus
    cancelable: bool
    amount_cents: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    created_at: datetime

    @field_validator("amount_cents", mode="before")
    @classmethod
    def _require_integer_cents(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("amount_cents 必须是以分为单位的整数")
        return value

    @field_validator("created_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at 必须带时区")
        return value.astimezone(UTC)
