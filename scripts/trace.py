#!/usr/bin/env python3
"""验收标准（AC）追溯矩阵：需求 → 任务 → 执行卡 → 测试。

检查器只保证“AC 在 tasks.md 里被提到”，本脚本检查“AC 有没有真实测试”。
未覆盖的 AC 必须登记在 scripts/trace-baseline.txt，并写明承接任务；
基线一旦被测试覆盖，必须删除该行，防止基线变成永久豁免。

用法：
    python3 scripts/trace.py            # 打印矩阵
    python3 scripts/trace.py --strict   # 存在未登记缺口或过期基线时退出码 1
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "docs" / "specs"
CARDS = ROOT / "docs" / "tasks"
BASELINE = ROOT / "scripts" / "trace-baseline.txt"
AC_ID = re.compile(r"AC[-_](\d{2})")


def ac_from_requirements(path: Path) -> list[str]:
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| AC-"):
            ids.append(line.split("|")[1].strip())
    return sorted(set(ids))


def ac_from_tests() -> dict[str, list[str]]:
    """只统计测试用例名里的 AC，避免把注释/文档字符串当成覆盖证据。"""
    found: dict[str, set[str]] = {}
    roots = [ROOT / "tests", ROOT / "apps" / "web" / "tests"]
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or "node_modules" in path.parts:
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.lstrip()
                is_test_case = stripped.startswith(("def test_", "async def test_"))
                is_test_case = is_test_case or stripped.startswith(
                    ("it(", "test(", "it.only(", "test.each")
                )
                if not is_test_case:
                    continue
                for ac in AC_ID.findall(line):
                    found.setdefault(f"AC-{ac}", set()).add(str(path.relative_to(ROOT)))
    return {ac: sorted(files) for ac, files in found.items()}


def ac_from_cards() -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for path in CARDS.rglob("T-*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- 绑定验收："):
                for ac in AC_ID.findall(line):
                    found.setdefault(f"AC-{ac}", set()).add(path.name)
    return {ac: sorted(files) for ac, files in found.items()}


def read_baseline() -> dict[str, str]:
    if not BASELINE.exists():
        return {}
    entries: dict[str, str] = {}
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        ac, _, reason = line.partition(":")
        entries[ac.strip()] = reason.strip()
    return entries


def main() -> int:
    strict = "--strict" in sys.argv
    requirements = [p for p in SPECS.glob("*/requirements.md")] + [
        p for p in SPECS.glob("*/brief.md")
    ]
    if not requirements:
        print("没有找到需求文档")
        return 1

    tests = ac_from_tests()
    cards = ac_from_cards()
    baseline = read_baseline()
    errors: list[str] = []
    rows: list[tuple[str, int, str]] = []

    for path in sorted(requirements):
        acs = ac_from_requirements(path)
        for ac in acs:
            count = len(tests.get(ac, []))
            card = ",".join(cards.get(ac, [])) or "-"
            rows.append((ac, count, card))
            if count == 0:
                if ac not in baseline:
                    errors.append(f"{ac}：没有测试引用，也不在 scripts/trace-baseline.txt 中")
            elif ac in baseline:
                errors.append(f"{ac}：已有测试，基线豁免必须删除")

    known = {row[0] for row in rows}
    for ac in sorted(set(tests) - known):
        errors.append(f"{ac}：测试引用了需求中不存在的验收编号")

    print("AC     测试数  执行卡")
    for ac, count, card in rows:
        flag = "" if count or ac in baseline else "  <- 缺口"
        print(f"{ac}   {count:>4}   {card}{flag}")
    if baseline:
        print("\n已登记基线（未覆盖，待承接）：")
        for ac, reason in baseline.items():
            print(f"  {ac}: {reason}")

    if errors:
        print(f"\n追溯检查失败，{len(errors)} 个问题：")
        for item in errors:
            print("  - " + item)
        return 1 if strict else 0

    print(f"\n追溯检查通过：{len(rows)} 条 AC，{len(baseline)} 条已登记基线。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
