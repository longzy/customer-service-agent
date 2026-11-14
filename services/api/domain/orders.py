"""订单领域类型。M1 只把 PAID_UNFULFILLED 视为可取消。"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UTC_ISO_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"


class OrderStatus(StrEnum):
    PAID_UNFULFILLED = "PAID_UNFULFILLED"
    FULFILLING = "FULFILLING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


def is_cancelable(status: OrderStatus) -> bool:
    """M1 的取消资格只取决于订单状态；归属与租户由授权层负责。"""
    return status is OrderStatus.PAID_UNFULFILLED


def _require_integer_cents(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("金额必须是以分为单位的整数")
    return value


def _require_utc_string(value: Any) -> str:
    """Wire 格式统一为带 Z 的 ISO 8601 字符串，不接受偏移量或时间戳数字。"""
    import re

    if not isinstance(value, str) or not re.fullmatch(UTC_ISO_PATTERN, value):
        raise ValueError("时间必须是形如 2026-11-14T06:02:00Z 的 UTC 字符串")
    return value


class _OrderBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    item_summary: str = Field(min_length=1)
    order_status: OrderStatus
    cancelable: bool
    amount_cents: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    created_at: datetime

    @field_validator("amount_cents", mode="before")
    @classmethod
    def _integer_cents(cls, value: Any) -> Any:
        return _require_integer_cents(value)

    @field_validator("created_at", mode="before")
    @classmethod
    def _utc_string(cls, value: Any) -> Any:
        return _require_utc_string(value)

    @field_validator("created_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _cancelable_matches_status(self) -> Self:
        if self.cancelable is not is_cancelable(self.order_status):
            raise ValueError("cancelable 必须由 order_status 推导，不能与之矛盾")
        return self


class OrderSummary(_OrderBase):
    """订单摘要。金额只用整数分，时间统一为 UTC 字符串。"""


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    unit_amount_cents: int = Field(ge=0)

    @field_validator("unit_amount_cents", mode="before")
    @classmethod
    def _integer_cents(cls, value: Any) -> Any:
        return _require_integer_cents(value)


class OrderDetail(_OrderBase):
    """订单详情：摘要字段 + 商品明细 + 可空的时间。"""

    items: list[OrderItem]
    paid_at: datetime | None
    shipped_at: datetime | None

    @field_validator("paid_at", "shipped_at", mode="before")
    @classmethod
    def _optional_utc_string(cls, value: Any) -> Any:
        if value is None:
            return None
        return _require_utc_string(value)

    @field_validator("paid_at", "shipped_at")
    @classmethod
    def _optional_to_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else value.astimezone(UTC)
