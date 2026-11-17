"""F-03：关键词归一化与交接单脱敏的纯函数边界（AC-32）。"""

import pytest

from backend.conversations.handoffs import match_handoff_keyword, normalize_text, redact_text


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("转人工", "转人工"),
        ("人工客服", "人工客服"),
        ("真人", "真人"),
        ("找人工", "找人工"),
        ("我要转 人工！", "转人工"),
        ("转，人工", "转人工"),
        ("转-人工", "转人工"),
        ("转\n人工", "转人工"),
        ("转人工，谢谢", "转人工"),
        ("转人工！？", "转人工"),
    ],
)
def test_关键词归一化后命中_AC_32(content: str, expected: str) -> None:
    assert match_handoff_keyword(content) == expected


@pytest.mark.parametrize("content", ["你好", "人工", "转接", "真", "订单到哪了"])
def test_未命中关键词返回空_AC_32(content: str) -> None:
    assert match_handoff_keyword(content) is None


def test_归一化丢弃空白标点保留正文_AC_32() -> None:
    assert normalize_text(" 转，人\n工！ ") == "转人工"
    assert normalize_text("ＡＢＣ　１２３") == "abc123"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("13800138000", "138****8000"),
        ("+8613800138000", "138****8000"),
        ("+86 138 0013 8000", "138****8000"),
        ("138 0013 8000", "138****8000"),
        ("138-0013-8000", "138****8000"),
        ("１３８００１３８０００", "138****8000"),
        ("110101199001011234", "110101********1234"),
        ("11010119900101123X", "110101********123X"),
        ("11010119900101123x", "110101********123x"),
        ("110101 1990 0101 1234", "110101********1234"),
        ("110101-1990-0101-1234", "110101********1234"),
        ("110101 1990 0101 123X", "110101********123X"),
        ("11010119900101123Ｘ", "110101********123X"),
        ("138.0013.8000", "138****8000"),
        ("(138) 0013-8000", "138****8000"),
        ("ALICE@EXAMPLE.COM", "A***@EXAMPLE.COM"),
    ],
)
def test_脱敏覆盖常见写法_AC_32(raw: str, expected: str) -> None:
    assert redact_text(raw) == expected


def test_脱敏不改变无敏感信息的正文_AC_32() -> None:
    assert redact_text("你好，订单 ORD-10001 还没到。") == "你好，订单 ORD-10001 还没到。"
    assert redact_text("全角＋－　１２３") == "全角＋－　１２３"
