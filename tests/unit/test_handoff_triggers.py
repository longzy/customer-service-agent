"""F-04：低置信/问订单/超范围转人工规则的纯函数边界（AC-32）。"""

import pytest

from backend.conversations.handoffs import (
    HANDOFF_CONFIDENCE_THRESHOLD,
    decide_model_handoff,
    match_out_of_scope_term,
)


def test_低置信阈值固定为0_6_AC_32() -> None:
    assert HANDOFF_CONFIDENCE_THRESHOLD == 0.6


@pytest.mark.parametrize(
    ("content", "term"),
    [
        ("我的订单到哪了", "订单"),
        ("订 单怎么还没到", "订单"),
        ("快递到哪了", "快递"),
        ("我要退款", "退款"),
        ("取消一下", "取消"),
        ("发票怎么开", "发票"),
        ("我要投诉", "投诉"),
        ("预计明天送达", "送达"),
        ("配送员到哪了", "配送"),
    ],
)
def test_订单与超范围文本命中_AC_32(content: str, term: str) -> None:
    assert match_out_of_scope_term(content) == term
    decision = decide_model_handoff(
        content=content, intent="UNKNOWN", confidence=0.95, reply="您好。"
    )
    assert decision is not None
    assert (decision.reason, decision.trigger) == ("OUT_OF_SCOPE", "out_of_scope")
    assert term in decision.summary_hint


@pytest.mark.parametrize("content", ["你好", "今天天气不错", "谢谢"])
def test_普通文本不命中超范围_AC_32(content: str) -> None:
    assert match_out_of_scope_term(content) is None


@pytest.mark.parametrize("intent", ["HUMAN_HANDOFF", "human_handoff", "TRANSFER", "transfer"])
def test_模型转人工意图触发低置信交接_AC_32(intent: str) -> None:
    decision = decide_model_handoff(
        content="找个同事帮忙看看", intent=intent, confidence=0.95, reply="好的。"
    )
    assert decision is not None
    assert (decision.reason, decision.trigger) == ("LOW_CONFIDENCE", "model_intent")
    assert decision.summary_hint


@pytest.mark.parametrize("confidence", [0.0, 0.59])
def test_置信度低于阈值触发低置信交接_AC_32(confidence: float) -> None:
    decision = decide_model_handoff(
        content="你好", intent="UNKNOWN", confidence=confidence, reply="您好。"
    )
    assert decision is not None
    assert (decision.reason, decision.trigger) == ("LOW_CONFIDENCE", "low_confidence")
    assert "置信" in decision.summary_hint


@pytest.mark.parametrize("confidence", [0.6, 0.95])
def test_置信度达到阈值不触发_AC_32(confidence: float) -> None:
    assert (
        decide_model_handoff(
            content="你好", intent="UNKNOWN", confidence=confidence, reply="您好。"
        )
        is None
    )


@pytest.mark.parametrize(
    "intent",
    ["QUERY_ORDER", "QUERY_RECENT", "CANCEL_ORDER", "CONFIRM_CANCEL", "OUT_OF_SCOPE"],
)
def test_模型超范围意图触发超范围交接_AC_32(intent: str) -> None:
    decision = decide_model_handoff(
        content="帮我看看那个东西", intent=intent, confidence=0.97, reply="好的。"
    )
    assert decision is not None
    assert (decision.reason, decision.trigger) == ("OUT_OF_SCOPE", "out_of_scope_intent")


@pytest.mark.parametrize(
    "reply",
    [
        "您的订单 ORD-10001 已发货。",
        "请提供订单号，我帮您查。",
        "退款会在 3 天内到账。",
        "预计明天送达。",
    ],
)
def test_模型回复涉及订单与超范围内容被拦截_AC_32(reply: str) -> None:
    decision = decide_model_handoff(
        content="你好呀", intent="UNKNOWN", confidence=0.98, reply=reply
    )
    assert decision is not None
    assert (decision.reason, decision.trigger) == ("OUT_OF_SCOPE", "model_out_of_scope")


@pytest.mark.parametrize("reply", ["查询结果：ORD-10001", "ORD-20002"])
def test_模型回复只含订单号也被拦截_AC_32(reply: str) -> None:
    decision = decide_model_handoff(
        content="你好呀", intent="UNKNOWN", confidence=0.98, reply=reply
    )
    assert decision is not None
    assert (decision.reason, decision.trigger) == ("OUT_OF_SCOPE", "model_out_of_scope")
    assert "订单号" in decision.summary_hint


def test_普通高置信回复不触发交接_AC_32() -> None:
    assert (
        decide_model_handoff(
            content="你好",
            intent="UNKNOWN",
            confidence=0.9,
            reply="您好，请问有什么可以帮您？",
        )
        is None
    )


def test_文本超范围优先于低置信与转人工意图_AC_32() -> None:
    decision = decide_model_handoff(
        content="我的订单到哪了", intent="HUMAN_HANDOFF", confidence=0.1, reply="好的。"
    )
    assert decision is not None
    assert (decision.reason, decision.trigger) == ("OUT_OF_SCOPE", "out_of_scope")
