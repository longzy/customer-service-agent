"""限速测试的固定窗口工具。

固定窗口按 wall-clock 对齐；不冻结时间时，"连续 N 次失败触发限速"的用例
一旦跨过窗口边界（分钟/15 分钟），计数会落进两个桶而漏触发。把时钟钉在
窗口内靠前位置即可消除这类偶发失败。
"""

from datetime import UTC, datetime

import pytest


def freeze_rate_limit_window(
    monkeypatch: pytest.MonkeyPatch, *, now: datetime | None = None
) -> datetime:
    """冻结客户/员工会话时间到当前窗口内靠前位置，返回固定时间。

    两个 `utc_now` 一起冻结：登录限速读 `employee_sessions.utc_now` 或
    `customer_sessions.utc_now`，消息限速读 `customer_sessions.utc_now`。
    """
    fixed = now or datetime.now(UTC).replace(second=5, microsecond=0)
    monkeypatch.setattr("backend.identity.customer_sessions.utc_now", lambda: fixed)
    monkeypatch.setattr("backend.identity.employee_sessions.utc_now", lambda: fixed)
    return fixed
