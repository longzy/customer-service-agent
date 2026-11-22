"""订单 Wire 校验：金额必须是整数分，时间必须是带 Z 的 UTC 字符串。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.domain.orders import OrderSummary, _require_integer_cents, _require_utc_string


def test_金额拒绝布尔与浮点_基座豁免() -> None:
    for value in (True, False, 1.5, "100"):
        with pytest.raises(ValueError, match="金额必须是以分为单位的整数"):
            _require_integer_cents(value)
    assert _require_integer_cents(0) == 0


def test_时间拒绝偏移与时间戳_基座豁免() -> None:
    for value in ("2026-11-14T06:02:00+08:00", datetime.now(UTC), 1760000000):
        with pytest.raises(ValueError, match="时间必须是形如 2026-11-14T06:02:00Z 的 UTC 字符串"):
            _require_utc_string(value)
    assert _require_utc_string("2026-11-14T06:02:00Z") == "2026-11-14T06:02:00Z"


def test_订单摘要拒绝非法金额与时间_基座豁免() -> None:
    base = {
        "order_id": "ORD-1",
        "item_summary": "商品",
        "order_status": "PAID_UNFULFILLED",
        "cancelable": True,
        "amount_cents": 100,
        "currency": "CNY",
        "created_at": "2026-11-14T06:02:00Z",
    }
    with pytest.raises(ValidationError):
        OrderSummary(**{**base, "amount_cents": True})
    with pytest.raises(ValidationError):
        OrderSummary(**{**base, "created_at": "2026-11-14T06:02:00+08:00"})
    assert OrderSummary(**base).amount_cents == 100
