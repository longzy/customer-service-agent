"""开发期员工身份与会话（纯身份，不依赖 FastAPI）。

账号固定为两个租户各两人；会话保存在内存中，仅用于开发与测试。
换真实身份提供方时，替换本模块实现即可，接口保持不变。
HTTP 中间件在 `services/api/auth_web.py`。
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

SESSION_COOKIE = "sid"
SESSION_TTL = timedelta(hours=8)


@dataclass(frozen=True)
class Identity:
    account_id: str
    user_id: str
    tenant_id: str
    display_name: str
    tenant_name: str


TENANT_NAMES = {"tenant-a": "示例商户 A", "tenant-b": "示例商户 B"}

ACCOUNTS: dict[str, Identity] = {
    "zhang-ming": Identity("zhang-ming", "user-a1", "tenant-a", "张明", "示例商户 A"),
    "li-hua": Identity("li-hua", "user-a2", "tenant-a", "李华", "示例商户 A"),
    "wang-qiang": Identity("wang-qiang", "user-b1", "tenant-b", "王强", "示例商户 B"),
    "zhao-min": Identity("zhao-min", "user-b2", "tenant-b", "赵敏", "示例商户 B"),
}

_sessions: dict[str, tuple[Identity, datetime]] = {}


def create_session(account_id: str) -> tuple[str, Identity] | None:
    identity = ACCOUNTS.get(account_id)
    if identity is None:
        return None
    sid = secrets.token_urlsafe(32)
    _sessions[sid] = (identity, datetime.now(UTC) + SESSION_TTL)
    return sid, identity


def get_session(sid: str | None) -> Identity | None:
    if not sid:
        return None
    entry = _sessions.get(sid)
    if entry is None:
        return None
    identity, expires_at = entry
    if expires_at <= datetime.now(UTC):
        _sessions.pop(sid, None)
        return None
    return identity


def destroy_session(sid: str | None) -> None:
    if sid:
        _sessions.pop(sid, None)
