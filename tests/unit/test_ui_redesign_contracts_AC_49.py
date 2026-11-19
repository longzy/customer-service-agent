"""002 UI 改版的规范收口：无 !important、id 选择器与新全局类。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "apps"
ID_SELECTOR = re.compile(r"^\s*#[A-Za-z_][\w-]*\s*\{", re.MULTILINE)


def _css_files() -> list[Path]:
    files: list[Path] = []
    for app in ("chat", "workspace"):
        files.extend((APPS / app / "app").glob("*.css"))
    return files


def test_no_important_or_id_selectors_AC_49() -> None:
    """全局 CSS 不使用 !important 或 id 选择器。"""
    for path in _css_files():
        text = path.read_text(encoding="utf-8")
        assert "!important" not in text, path
        assert ID_SELECTOR.search(text) is None, path


def test_globals_only_keep_tailwind_entry_AC_49() -> None:
    """globals.css 只保留 Tailwind 入口、@theme 与 html/body 基础排版。"""
    for app in ("chat", "workspace"):
        text = (APPS / app / "app" / "globals.css").read_text(encoding="utf-8")
        class_rules = [
            line for line in text.splitlines() if re.match(r"^\.[A-Za-z_-][\w-]*\s*\{", line)
        ]
        assert class_rules == [], app
