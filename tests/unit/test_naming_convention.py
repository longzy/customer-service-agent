"""测试命名与验收编号规范：覆盖 tests/ 全目录。"""

import re
from pathlib import Path

REQUIREMENTS = Path("docs/specs/001-order-cancel/requirements.md")
AC_PATTERN = re.compile(r"_AC_(\d{2})")
DEF_PATTERN = re.compile(r"^def (test_\w+)", re.MULTILINE)


def _test_files() -> list[Path]:
    return sorted(path for path in Path("tests").rglob("test_*.py") if path.is_file())


def known_acs() -> set[str]:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    return set(re.findall(r"\| (AC-\d{2}) \|", text))


def test_禁止连字符形式的验收编号() -> None:
    """连字符写法不是合法标识符，会让整个文件收集失败。"""
    forbidden = "_AC" + "-"
    offenders = [
        str(path) for path in _test_files() if forbidden in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"以下文件使用连字符写法（应改为下划线）：{offenders}"


def test_验收编号必须存在() -> None:
    acs = known_acs()
    assert acs, "未从需求文档解析到任何验收编号"
    unknown: list[str] = []
    for path in _test_files():
        for name in DEF_PATTERN.findall(path.read_text(encoding="utf-8")):
            for number in AC_PATTERN.findall(name):
                if f"AC-{number}" not in acs:
                    unknown.append(f"{path}::{name}")
    assert unknown == [], f"测试引用了不存在的验收编号：{unknown}"


def test_验收后缀写法一致() -> None:
    """含 AC 的测试名必须是 `_AC_数字` 或 `_基座豁免`，不能自造写法。"""
    bad: list[str] = []
    for path in _test_files():
        for name in DEF_PATTERN.findall(path.read_text(encoding="utf-8")):
            if "_AC" not in name and "基座豁免" not in name:
                continue
            valid = AC_PATTERN.search(name) or name.endswith("_基座豁免")
            if not valid:
                bad.append(f"{path}::{name}")
    assert bad == [], f"验收后缀写法不规范：{bad}"
