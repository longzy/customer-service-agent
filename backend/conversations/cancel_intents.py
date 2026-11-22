"""取消意图与固定确认短语的确定性判定（F-32）。

模型只负责理解与解释；一条客户消息是否进入取消分支、是否构成客户确认，
都由这里的词表与正则决定，测试直接驱动同一组函数（AC-63）。
"""

from __future__ import annotations

import re

from backend.conversations.handoffs import normalize_text
from backend.conversations.order_queries import NON_QUERY_TERMS, extract_order_ids

# 明确指向“取消”这个动作的短语。单独一个“取消”只在整句就是“取消”时才算，
# 避免“取消会怎样”这类询问被当成要发起取消。
CANCEL_INTENT_PHRASES = (
    "取消订单",
    "取消这单",
    "取消该订单",
    "取消单号",
    "取消一下",
    "这单不要了",
    "这单不想要了",
    "不要这单",
    "不想要了",
    "我要取消",
    "我想取消",
    "帮我取消",
    "直接取消",
    "取消吧",
)

# “取消 + 订单指代”同现（如“取消我的订单”）也算明确取消意图。
CANCEL_TARGET_TERMS = ("订单", "这单", "该单", "单号", "下单", "购买")

# 问的是已完成/过去的取消（“查一下已取消的订单”），不是要发起取消。
CANCEL_PAST_TERMS = ("已取消", "已经取消", "取消过")

# 疑问/咨询（“怎么取消/取消会怎样/取消订单后多久到账”）交给模型解释，不替客户发起。
CANCEL_QUESTION_TERMS = (
    "怎么",
    "怎样",
    "如何",
    "能否",
    "会不会",
    "多久",
    "什么时候",
    "几天",
    "到账",
    "在哪",
    "哪里",
    "记录",
    "历史",
    "明细",
    "吗",
)

# 这些词表示客户在问别的操作：命中就不进取消分支，保持 001 的转人工路径。
# 与订单查询共用一份超范围词表，只把“取消”本身排除。
CANCEL_EXCLUDE_TERMS = tuple(term for term in NON_QUERY_TERMS if term != "取消")

# 固定确认短语（Q-4）：容忍“好的/嗯”前缀、全角标点与“订单/这单”后缀。
# 必须整句匹配，避免“确认取消会退款吗”这类追问被当成确认。
CONFIRM_CANCEL_PATTERN = re.compile(
    r"^(?:(?:好的|嗯|是的)?(?:确认|确定)取消|(?:是的|对|好|嗯)取消)(?:订单|这单|该订单)?$"
)


def has_cancel_intent(text: str) -> bool:
    """客户是否在明确要求取消订单；退款/退货/咨询问句仍返回 False。"""
    normalized = normalize_text(text)
    if any(normalize_text(term) in normalized for term in CANCEL_EXCLUDE_TERMS):
        return False
    if any(term in normalized for term in CANCEL_PAST_TERMS):
        return False
    if any(term in normalized for term in CANCEL_QUESTION_TERMS):
        return False
    if normalized == "取消":
        return True
    if "取消" in normalized and (
        extract_order_ids(text) or any(term in normalized for term in CANCEL_TARGET_TERMS)
    ):
        return True
    return any(normalize_text(phrase) in normalized for phrase in CANCEL_INTENT_PHRASES)


def match_confirm_cancel_phrase(text: str) -> str | None:
    """返回命中的固定确认短语（归一化后）；不是确认则返回 None。"""
    normalized = normalize_text(text)
    if CONFIRM_CANCEL_PATTERN.match(normalized):
        return normalized
    return None
