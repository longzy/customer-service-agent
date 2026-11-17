"""认证共用：UTC 时钟与 session token 哈希。"""

import hashlib
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    """token 只以 SHA-256 入库；256-bit 随机量无需再加盐。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
