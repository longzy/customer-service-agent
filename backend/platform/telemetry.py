"""OTel/W3C trace context 兼容：UUID 内部标识与 32/16 hex 互转。"""

from __future__ import annotations

import hashlib
import re
import uuid

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$", re.IGNORECASE)
_HEX16 = re.compile(r"^[0-9a-f]{16}$", re.IGNORECASE)


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    """解析 W3C traceparent；返回 (UUID trace_id, parent span hex)。非法/全零忽略。"""
    if not value:
        return None
    match = _TRACEPARENT.fullmatch(value.strip())
    if match is None:
        return None
    trace_hex, span_hex, _flags = match.groups()
    if trace_hex == "0" * 32 or span_hex == "0" * 16:
        return None
    return str(uuid.UUID(trace_hex)), span_hex.lower()


def to_otel_trace_id(trace_id: str) -> str:
    """内部 UUID/字符串 trace id 转 32 hex；非 UUID 时用稳定哈希。"""
    try:
        return uuid.UUID(str(trace_id)).hex
    except (ValueError, AttributeError):
        return hashlib.sha256(str(trace_id).encode("utf-8")).hexdigest()[:32]


def to_otel_span_id(span_id: str) -> str:
    """内部 span id 转 16 hex；已是 16 hex 时原样返回。"""
    raw = str(span_id).lower()
    if _HEX16.fullmatch(raw):
        return raw
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def format_traceparent(trace_id: str, span_id: str, flags: str = "01") -> str:
    return f"00-{to_otel_trace_id(trace_id)}-{to_otel_span_id(span_id)}-{flags}"
