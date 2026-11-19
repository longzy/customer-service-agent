"""PostgreSQL 固定窗口限速；先记一次尝试，再判定是否超限。

- 桶键与窗口由调用方决定（客户登录、员工登录、消息各自独立）。
- 超限抛 `RateLimitedError`；桶本身已提交，调用方不再重复计数。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert

from backend.platform.db import session_factory
from backend.platform.models import ServiceRateLimitBucket


class RateLimitedError(Exception):
    """请求次数超过窗口上限。"""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate limited")
        self.retry_after_seconds = retry_after_seconds


def fixed_window_start(now: datetime, window: timedelta) -> datetime:
    """按整数秒对齐窗口，避免浮点误差把同一窗口拆成多个桶。"""
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


async def consume_fixed_window(
    *,
    bucket_key: str,
    limit: int,
    window: timedelta,
    now: datetime,
) -> None:
    """独立事务记一次尝试；业务回滚不退还计数。"""
    start = fixed_window_start(now, window)
    statement = (
        insert(ServiceRateLimitBucket)
        .values(bucket_key=bucket_key, window_start=start, count=1)
        .on_conflict_do_update(
            index_elements=[
                ServiceRateLimitBucket.bucket_key,
                ServiceRateLimitBucket.window_start,
            ],
            set_={"count": ServiceRateLimitBucket.count + 1},
        )
        .returning(ServiceRateLimitBucket.count)
    )
    async with session_factory() as db:
        count = (await db.execute(statement)).scalar_one()
        await db.commit()
    if count > limit:
        retry_after = int((start + window - now).total_seconds())
        raise RateLimitedError(max(retry_after, 1))
