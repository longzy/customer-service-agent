#!/usr/bin/env python3
"""解析评审记录 `## 结论` 的首句判定。

只认结论节第一个非空行开头的判定词（通过 / 有条件通过 / 不通过），
避免把“首轮不通过（已关闭）”这类历史轮次描述误判成最终结论。
`close_feature.py` 与 `check-review-prereqs.py` 共用本解析，保持同一口径。
"""

from __future__ import annotations

import re

VERDICT = re.compile(r"^(?:结论[:：]\s*)?(?P<verdict>不通过|有条件通过|通过)")


def section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def conclusion_verdict(text: str) -> str | None:
    """返回 `通过` / `有条件通过` / `不通过`；结论节没有判定词时返回 None。"""
    for line in section(text, "结论").splitlines():
        stripped = line.strip().lstrip("*_ ").rstrip("*_ ")
        if not stripped:
            continue
        match = VERDICT.match(stripped)
        return match.group("verdict") if match else None
    return None
