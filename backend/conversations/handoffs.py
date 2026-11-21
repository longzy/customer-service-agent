"""转人工触发与完整交接单构造。

- 关键词命中优先于模型调用；命中后不请求模型。
- 交接单只保存脱敏后的摘要与上下文：最近 20 条消息、正文合计 ≤4000 字、AI 轨迹。
- AI 轨迹只保存事件元数据，不保存 prompt/response 正文（plan 3.3.4）。
- 本模块只 flush，由 API 层统一 commit。
"""

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent_runtime.types import Intent
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

# 交接单订单上下文状态（F-28）：区分“有订单 / 查无 / 查询不可用”，
# 让坐席看到“暂无订单”与“订单信息暂不可用”是两件事（AC-56）。
OrderContextStatus = Literal["ok", "empty", "failed"]
ORDER_CONTEXT_OK: OrderContextStatus = "ok"
ORDER_CONTEXT_EMPTY: OrderContextStatus = "empty"
ORDER_CONTEXT_FAILED: OrderContextStatus = "failed"

# plan 3.3.4：关键词未命中时，由模型 intent/confidence 与确定性规则共同判定转人工
HANDOFF_CONFIDENCE_THRESHOLD = 0.6
# 模型自述“要人工”：HUMAN_HANDOFF 是 Prompt 约定值，TRANSFER 兼容同义输出
TRANSFER_INTENTS = frozenset({Intent.HUMAN_HANDOFF.value, "TRANSFER"})
# 取消/退款与真正的超范围意图仍转人工；订单查询意图已由 F-26 的订单分支承接。
OUT_OF_SCOPE_INTENTS = frozenset(
    {
        Intent.CANCEL_ORDER.value,
        Intent.CONFIRM_CANCEL.value,
        "OUT_OF_SCOPE",
    }
)
# 常见订单/交易/售后诉求：即使模型误判为 UNKNOWN 也由确定性规则转人工。
# “订单/单号”不在此列：F-26 起由订单查询分支处理，闲聊带“订单”不建单（AC-52）。
OUT_OF_SCOPE_TERMS = (
    "物流",
    "快递",
    "包裹",
    "发货",
    "收货",
    "签收",
    "送达",
    "配送",
    "派送",
    "到货",
    "运输",
    "退款",
    "退货",
    "换货",
    "取消",
    "发票",
    "支付",
    "付款",
    "扣款",
    "银行卡",
    "转账",
    "投诉",
    "售后",
)
# 模型回复不再因单独出现“订单/单号”而转人工：F-26 起闲聊带“订单”必须是
# 不建单的正常回复（AC-52）；回复里的订单号与物流/退款等具体事实仍被拦截。
# 回复同时提到订单与下列事实词时，视为模型在编造订单事实（AC-54）。
REPLY_ORDER_FACT_TERMS = (
    "金额",
    "价格",
    "多少钱",
    "元",
    "明天",
    "今天",
    "后天",
    "预计",
    "正在",
    "已处理",
    "已发货",
    "已到",
    "路上",
    "签收",
    "备货",
)
ORDER_ID_PATTERN = re.compile(r"(?<![A-Za-z0-9-])ORD-\d{4,12}(?![\d-])", re.IGNORECASE)


@dataclass(frozen=True)
class HandoffDecision:
    """一次模型输出触发的转人工决定；摘要给坐席看，不含模型回复正文。"""

    reason: str
    trigger: str
    summary_hint: str


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


def _reply_order_fact(reply: str) -> str | None:
    """回复同时提到订单/单号与价格、时间或履约状态时，返回命中的事实词。

    单独提到“订单/单号”是正常引导（AC-52 不建单）；与事实词同现才视为
    模型在编造订单信息（AC-54）。
    """
    normalized = normalize_text(reply)
    if "订单" not in normalized and "单号" not in normalized:
        return None
    return next(
        (term for term in REPLY_ORDER_FACT_TERMS if normalize_text(term) in normalized),
        None,
    )


def match_out_of_scope_term(text: str, terms: tuple[str, ...] = OUT_OF_SCOPE_TERMS) -> str | None:
    """返回命中的订单/超范围词；归一化后匹配，容忍空格与中文标点。"""
    normalized = normalize_text(text)
    return next(
        (term for term in terms if normalize_text(term) in normalized),
        None,
    )


def decide_model_handoff(
    *, content: str, intent: str, confidence: float, reply: str
) -> HandoffDecision | None:
    """判定关键词未命中的模型输出是否转人工（plan 3.3.4）。

    优先级：订单/超范围文本 > 模型转人工意图 > 模型超范围意图 > 低置信 >
    模型回复含订单号/超范围内容。文本与回复规则是确定性护栏：订单查询由
    F-26 的订单分支（服务端确定性执行）承接，模型回复里的订单事实不可信；
    回复出现订单号或物流/退款等具体事实直接丢弃并转人工。单独提到“订单”
    不再拦截，避免闲聊带“订单”被误建单（003 AC-52）。
    """
    matched_term = match_out_of_scope_term(content)
    if matched_term is not None:
        return HandoffDecision(
            reason="OUT_OF_SCOPE",
            trigger="out_of_scope",
            summary_hint=f"问题超出 AI 处理范围（命中“{matched_term}”），已自动转人工",
        )

    normalized_intent = intent.strip().upper()
    if normalized_intent in TRANSFER_INTENTS:
        return HandoffDecision(
            reason="LOW_CONFIDENCE",
            trigger="model_intent",
            summary_hint="客户表达了转人工意愿，已自动转人工",
        )
    if normalized_intent in OUT_OF_SCOPE_INTENTS:
        return HandoffDecision(
            reason="OUT_OF_SCOPE",
            trigger="out_of_scope_intent",
            summary_hint=f"模型判定为超范围问题（{normalized_intent}），已自动转人工",
        )
    if confidence < HANDOFF_CONFIDENCE_THRESHOLD:
        return HandoffDecision(
            reason="LOW_CONFIDENCE",
            trigger="low_confidence",
            summary_hint=f"AI 置信度不足（{confidence:.2f}），已自动转人工",
        )

    reply_term = match_out_of_scope_term(reply)
    reply_fact = _reply_order_fact(reply)
    if reply_term is not None or ORDER_ID_PATTERN.search(reply) or reply_fact is not None:
        if reply_term is not None:
            detail = f"命中“{reply_term}”"
        elif reply_fact is not None:
            detail = f"订单事实“{reply_fact}”"
        else:
            detail = "包含订单号"
        return HandoffDecision(
            reason="OUT_OF_SCOPE",
            trigger="model_out_of_scope",
            summary_hint=f"模型回复涉及超范围内容（{detail}），已自动转人工",
        )
    return None


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
    """脱敏手机号、邮箱与 18 位身份证号，兼容 +86、分隔符与全角数字。

    支持范围（契约）：大陆手机号（`+86`、空格/短横/点号/括号/全角数字）、
    邮箱、18 位身份证（含 `X/x` 与分隔符）。其他格式（银行卡、护照、座机、
    非大陆号码等）按原文透传，属于 004 安全硬化范围，不在 M1 承诺内。
    """
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
    failure_count: int | None = None,
    last_error: str | None = None,
    orders: list[dict[str, Any]] | None = None,
    order_context_status: OrderContextStatus | None = None,
) -> tuple[ServiceHandoff, bool]:
    """创建一张 open 交接单；已有 open 单时复用，避免撞部分唯一索引。

    返回 `(handoff, created)`：`created=False` 表示复用了既有 open 单，调用方不重复写
    `handoff.created` 审计。连续模型失败时写入失败次数与最后一次错误码。
    `orders` 是客户本人订单摘要快照（≤5 条，白名单字段）：AC-55 要求无订单时
    `order_count=0` 且不写空摘要，因此仅在非空时写入 context。
    """
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
        return existing, False

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

    status: OrderContextStatus = order_context_status or (
        ORDER_CONTEXT_OK if orders else ORDER_CONTEXT_EMPTY
    )
    context: dict[str, object] = {
        "order_count": len(orders) if orders else 0,
        "order_context_status": status,
        "trigger": trigger,
        "customer_username": username,
        "customer_display_name": display_name,
        "messages": messages,
        "ai_trace": await _ai_trace(db, conversation.id),
    }
    if orders:
        context["orders"] = orders
    if matched_keyword is not None:
        context["matched_keyword"] = matched_keyword
    if failure_count is not None:
        context["failure_count"] = failure_count
    if last_error is not None:
        context["last_error"] = last_error

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
    return handoff, True
