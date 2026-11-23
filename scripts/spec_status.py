#!/usr/bin/env python3
"""规格状态判定：草案 spec 暂不参与结构、AC 覆盖与追溯门禁。

规格在 Frame 阶段先落 `requirements.md`（状态：草案），批准后才进入
design/tasks 与门禁检查。三个脚本共用本判定，避免各自解析状态行而漂移。
"""

from __future__ import annotations

import re
from pathlib import Path

STATUS_LINE = re.compile(r"^- 状态：(.+)$", re.MULTILINE)
DRAFT_PREFIX = "草案"


def is_draft(requirements: Path) -> bool:
    """requirements 标为「草案」时返回 True；读不到或没有状态行按非草案处理。"""
    try:
        text = requirements.read_text(encoding="utf-8")
    except OSError:
        return False
    match = STATUS_LINE.search(text)
    return match is not None and match.group(1).strip().startswith(DRAFT_PREFIX)
