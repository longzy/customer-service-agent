"""转人工触发与完整交接单构造。

- 关键词命中优先于模型调用；命中后不请求模型。
- 交接单只保存脱敏后的摘要与上下文：最近 20 条消息、正文合计 ≤4000 字、AI 轨迹。
- AI 轨迹只保存事件元数据，不保存 prompt/response 正文（plan 3.3.4）。
- 本模块只 flush，由 API 层统一 commit。
"""

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.conversations.statuses import OPEN_HANDOFF_STATUSES, QUEUED
from backend.platform.models import (
    ServiceAiEvent,
    ServiceConversation,
    ServiceCustomer,
    ServiceHandoff,
    ServiceMessage,
)

# plan 3.3.4：关键词 normalize 后命中即直接转人工
HANDOFF_KEYWORDS = ("转人工", "人工客服", "真人", "找人工")
HANDOFF_MESSAGE_LIMIT = 20
HANDOFF_CONTEXT_CHAR_LIMIT = 4000
HANDOFF_SUMMARY_CHAR_LIMIT = 500
HANDOFF_AI_TRACE_LIMIT = 20
PENDING_STEP = "等待坐席接入"

# 只折叠数字相关全角字符用于匹配；输出仍按原文切片，非敏感正文不改写
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９＋－　Ｘｘ", "0123456789+- Xx")
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[\s.\-]?)?\(?(1[3-9]\d)\)?[\s.\-]?(?:\d{4})[\s.\-]?(\d{4})(?!\d)"
)
EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
ID_CARD_PATTERN = re.compile(
    r"(?<!\d)(\d{6})[\s.\-]?(\d{2})[\s.\-]?(\d{2})[\s.\-]?(\d{2})[\s.\-]?(\d{2})"
    r"[\s.\-]?(\d{3}[\dXx])(?!\d)"
)


def normalize_text(text: str) -> str:
    """NFKC + 小写，只保留字母/数字/组合符；空格、标点与符号全部丢弃。

    中文用户常在关键词中插入空格、全角标点或短横（如“转，人工”），
    归一化后统一做子串匹配。
    """
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", text).lower()
        if unicodedata.category(char)[0] in {"L", "N", "M"}
    )


def match_handoff_keyword(text: str) -> str | None:
    """返回命中的关键词；按 HANDOFF_KEYWORDS 顺序取第一个。"""
    normalized = normalize_text(text)
    return next((keyword for keyword in HANDOFF_KEYWORDS if keyword in normalized), None)


def _mask_matches(text: str, pattern: re.Pattern[str], mask: Callable[[re.Match[str]], str]) -> str:
    """在折叠后的副本上匹配，但按原文切片替换，避免改写非敏感正文。"""
    source = text.translate(_FULLWIDTH_DIGITS)
    parts: list[str] = []
    cursor = 0
    for match in pattern.finditer(source):
        parts.append(text[cursor : match.start()])
        parts.append(mask(match))
        cursor = match.end()
    if not parts:
        return text
    parts.append(text[cursor:])
    return "".join(parts)


def redact_text(text: str) -> str:
    """脱敏手机号、邮箱与 18 位身份证号，兼容 +86、分隔符与全角数字。"""
    redacted = _mask_matches(
        text, ID_CARD_PATTERN, lambda match: f"{match.group(1)}********{match.group(6)}"
    )
    redacted = _mask_matches(
        redacted, PHONE_PATTERN, lambda match: f"{match.group(1)}****{match.group(2)}"
    )
    return _mask_matches(
        redacted, EMAIL_PATTERN, lambda match: f"{match.group(1)}***@{match.group(2)}"
    )


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _summary(display_name: str, username: str, reason_label: str, last_content: str) -> str:
    summary = f"{display_name}（{username}）{reason_label}"
    if last_content:
        summary += f"；最近消息：{last_content}"
    return summary[:HANDOFF_SUMMARY_CHAR_LIMIT]


async def _customer_profile(db: AsyncSession, conversation: ServiceConversation) -> tuple[str, str]:
    row = (
        await db.execute(
            select(ServiceCustomer).where(
                ServiceCustomer.id == conversation.customer_id,
                ServiceCustomer.tenant_id == conversation.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return conversation.customer_id, conversation.customer_id
    return row.username, row.display_name


async def _recent_messages(db: AsyncSession, conversation_id: str) -> list[dict[str, object]]:
    """最近 20 条，按时间正序；正文从最新往前累计到 4000 字。"""
    rows = list(
        (
            await db.execute(
                select(ServiceMessage)
                .where(ServiceMessage.conversation_id == conversation_id)
                .order_by(ServiceMessage.id.desc())
                .limit(HANDOFF_MESSAGE_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    remaining = HANDOFF_CONTEXT_CHAR_LIMIT
    kept: list[dict[str, object]] = []
    for row in rows:
        if remaining <= 0:
            break
        content = redact_text(row.content)
        if len(content) > remaining:
            content = content[:remaining]
        kept.append(
            {
                "id": row.id,
                "author_type": row.author_type,
                "content": content,
                "created_at": _utc_text(row.created_at),
            }
        )
        remaining -= len(content)
    kept.reverse()
    return kept


async def _ai_trace(db: AsyncSession, conversation_id: str) -> list[dict[str, object]]:
    rows = list(
        (
            await db.execute(
                select(ServiceAiEvent)
                .where(ServiceAiEvent.conversation_id == conversation_id)
                .order_by(ServiceAiEvent.created_at.desc(), ServiceAiEvent.id.desc())
                .limit(HANDOFF_AI_TRACE_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "event_type": row.event_type,
            "name": row.name,
            "status": row.status,
            "confidence": row.confidence,
            "created_at": _utc_text(row.created_at),
        }
        for row in reversed(rows)
    ]


async def create_handoff(
    db: AsyncSession,
    conversation: ServiceConversation,
    *,
    reason: str,
    trigger: str,
    now: datetime,
    summary_hint: str = "",
    matched_keyword: str | None = None,
) -> ServiceHandoff:
    """创建一张 open 交接单；已有 open 单时复用，避免撞部分唯一索引。"""
    existing = (
        await db.execute(
            select(ServiceHandoff).where(
                ServiceHandoff.tenant_id == conversation.tenant_id,
                ServiceHandoff.conversation_id == conversation.id,
                ServiceHandoff.status.in_(OPEN_HANDOFF_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.updated_at = now
        return existing

    username, display_name = await _customer_profile(db, conversation)
    messages = await _recent_messages(db, conversation.id)
    last_customer = next(
        (item["content"] for item in reversed(messages) if item["author_type"] == "customer"),
        "",
    )
    if matched_keyword is not None:
        reason_label = f"要求转人工（命中关键词“{matched_keyword}”）"
    else:
        reason_label = summary_hint
    summary = _summary(display_name, username, reason_label, str(last_customer))

    context: dict[str, object] = {
        "order_count": 0,
        "trigger": trigger,
        "customer_username": username,
        "customer_display_name": display_name,
        "messages": messages,
        "ai_trace": await _ai_trace(db, conversation.id),
    }
    if matched_keyword is not None:
        context["matched_keyword"] = matched_keyword

    handoff = ServiceHandoff(
        id=str(uuid4()),
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        status=QUEUED,
        reason=reason,
        priority="normal",
        summary=summary,
        context=context,
        pending_step=PENDING_STEP,
        version=0,
        journey_id=conversation.journey_id,
        created_at=now,
        updated_at=now,
    )
    db.add(handoff)
    await db.flush()
    return handoff
