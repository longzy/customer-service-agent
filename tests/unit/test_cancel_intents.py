"""F-32：取消意图与固定确认短语的确定性判定（AC-63）。"""

import pytest

from backend.conversations.cancel_intents import has_cancel_intent, match_confirm_cancel_phrase


@pytest.mark.parametrize(
    "text",
    [
        "取消订单",
        "取消这单",
        "取消我的订单",
        "这单不要了",
        "取消 ORD-10001",
        "帮我取消",
        "取 消 订 单",
    ],
)
def test_明确取消意图进入取消分支_AC_63(text: str) -> None:
    assert has_cancel_intent(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "退款",
        "我要退款",
        "退货换货",
        "查订单",
        "我的订单",
        "你好",
        "取消会怎样",
        "怎么取消订单",
        "查一下已取消的订单",
        "取消订单后多久到账",
        "确认取消",
    ],
)
def test_退款与闲聊不进入取消分支_AC_63(text: str) -> None:
    assert has_cancel_intent(text) is False


@pytest.mark.parametrize(
    "text",
    ["确认取消", "确定取消", "是的，取消", "好的，确认取消", "嗯 确认取消"],
)
def test_固定短语识别为确认_AC_63(text: str) -> None:
    assert match_confirm_cancel_phrase(text) is not None


@pytest.mark.parametrize(
    "text",
    ["取消订单", "确认一下", "不想取消", "退款", "确认取消会退款吗"],
)
def test_非确认短语不构成确认_AC_63(text: str) -> None:
    assert match_confirm_cancel_phrase(text) is None
