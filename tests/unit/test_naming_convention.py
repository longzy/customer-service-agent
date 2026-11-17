"""测试命名与验收编号规范：覆盖 tests/ 全目录与全部规格。"""

import re
from pathlib import Path

SPECS = Path("docs/specs")
AC_PATTERN = re.compile(r"_AC_(\d{2})")
LEGACY_ACS = {f"AC-{number:02d}" for number in range(1, 30)}
TABLE_AC_PATTERN = re.compile(r"^\| (AC-\d{2}) \|", re.MULTILINE)
DEF_PATTERN = re.compile(r"^def (test_\w+)", re.MULTILINE)


def _test_files() -> list[Path]:
    return sorted(path for path in Path("tests").rglob("test_*.py") if path.is_file())


def _acceptance_files() -> list[Path]:
    return sorted(SPECS.glob("*/requirements.md")) + sorted(SPECS.glob("*/brief.md"))


def known_acs() -> set[str]:
    acs: set[str] = set()
    for path in _acceptance_files():
        acs |= set(TABLE_AC_PATTERN.findall(path.read_text(encoding="utf-8")))
    return acs


def duplicate_acs(paths: list[Path]) -> list[str]:
    """按原始出现次数查重；同文件重复与跨文件重复都要报告。"""
    seen: dict[str, Path] = {}
    duplicates: list[str] = []
    for path in paths:
        for ac in TABLE_AC_PATTERN.findall(path.read_text(encoding="utf-8")):
            if ac in seen:
                duplicates.append(f"{ac}: {seen[ac]} 与 {path}")
            else:
                seen[ac] = path
    return duplicates


def test_验收编号全局唯一() -> None:
    """AC 编号跨规格全局唯一；重复会让 trace 把两个 AC 当成同一个。"""
    duplicates = duplicate_acs(_acceptance_files())
    assert duplicates == [], f"验收编号重复：{duplicates}"


def test_验收编号同文件重复也会被拦下(tmp_path: Path) -> None:
    path = tmp_path / "requirements.md"
    path.write_text("| AC-99 | a | b | c |\n| AC-99 | d | e | f |\n", encoding="utf-8")

    assert duplicate_acs([path]) != []


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
                ac = f"AC-{number}"
                if ac not in acs and ac not in LEGACY_ACS:
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


def test_前端测试不使用连字符验收编号_基座豁免() -> None:
    forbidden = "_AC" + "-"
    offenders = [
        str(path)
        for path in Path("apps/web/tests").rglob("*.test.tsx")
        if forbidden in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"前端测试使用了连字符写法：{offenders}"
