"""002 UI 改版的前端资产契约：令牌单一来源与无颜色字面量。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPS = ROOT / "apps"
COLOR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(")
SOURCE_SUFFIXES = {".tsx", ".ts", ".css"}
TOKENS = ROOT / "docs" / "design-system" / "tokens.css"


def _source_files(app: str) -> list[Path]:
    roots = [APPS / app / "app", APPS / app / "components", APPS / app / "features"]
    files: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        files.extend(
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix in SOURCE_SUFFIXES
            and path.name not in {"tokens.css", "api-types.ts"}
        )
    return sorted(files)


def test_token_copies_match_source_AC_40() -> None:
    """两个应用只保留与唯一来源一致的令牌副本。"""
    source = TOKENS.read_text(encoding="utf-8")
    for app in ("chat", "workspace"):
        assert (APPS / app / "app" / "tokens.css").read_text(encoding="utf-8") == source


def test_globals_have_no_root_token_copy_AC_40() -> None:
    """globals.css 不再维护 :root 副本，只留 Tailwind 入口与 @theme。"""
    for app in ("chat", "workspace"):
        text = (APPS / app / "app" / "globals.css").read_text(encoding="utf-8")
        assert ":root" not in text
        assert COLOR_LITERAL.search(text) is None, app


def test_components_have_no_color_literals_AC_40() -> None:
    """组件与页面样式不写颜色字面量，一律引用令牌或 theme。"""
    offenders: list[str] = []
    for app in ("chat", "workspace"):
        for path in _source_files(app):
            if COLOR_LITERAL.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
