#!/usr/bin/env python3
"""验收标准（AC）追溯矩阵：需求 → feature → 执行卡 → 测试。

检查器只保证“AC 在 tasks.md 里被提到”，本脚本检查“AC 有没有真实测试”，
并按 feature 的 Passes 区分“完全覆盖”与“部分覆盖”：
- 没有测试的 AC 必须登记基线并写明承接任务；
- 有测试但仍有未通过 feature 的 AC 属于部分覆盖，也要登记基线；
- 所有承接 feature 都通过后，基线必须删除，防止永久豁免。

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
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
LEGACY_AC = {f"AC-{number:02d}" for number in range(1, 30)}


def ac_from_requirements(path: Path) -> list[str]:
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| AC-"):
            ids.append(line.split("|")[1].strip())
    return sorted(set(ids))


def frontend_header_acs(path: Path) -> set[str]:
    """前端测试文件头 `// AC-XX` 约定（FE-TEST-05）；只看前 5 行，避免正文误匹配。"""
    if path.suffix not in {".ts", ".tsx"}:
        return set()
    head = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:5]
    return {f"AC-{ac}" for line in head for ac in AC_ID.findall(line)}


def ac_from_tests() -> dict[str, list[str]]:
    """测试用例名里的 AC + 前端测试文件头的 `// AC-XX`；同一文件去重。"""
    found: dict[str, set[str]] = {}
    roots = [ROOT / "tests"] + sorted((ROOT / "apps").glob("*/tests"))
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or "node_modules" in path.parts:
                continue
            relative = str(path.relative_to(ROOT))
            for ac in frontend_header_acs(path):
                found.setdefault(ac, set()).add(relative)
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.lstrip()
                is_test_case = stripped.startswith(("def test_", "async def test_"))
                is_test_case = is_test_case or stripped.startswith(
                    ("it(", "test(", "it.only(", "test.each")
                )
                if not is_test_case:
                    continue
                for ac in AC_ID.findall(line):
                    found.setdefault(f"AC-{ac}", set()).add(relative)
    return {ac: sorted(files) for ac, files in found.items()}


def ac_from_cards() -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for path in CARDS.rglob("*.md"):
        if not re.match(r"^[TF]-\d{2}\.md$", path.name):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- 绑定验收："):
                for ac in AC_ID.findall(line):
                    found.setdefault(f"AC-{ac}", set()).add(path.name)
    return {ac: sorted(files) for ac, files in found.items()}


def ac_from_features() -> dict[str, list[tuple[str, bool]]]:
    """AC → 承接它的执行卡与是否完成；状态源是执行卡 frontmatter。"""
    found: dict[str, list[tuple[str, bool]]] = {}
    for path in sorted(CARDS.rglob("F-*.md")):
        match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
        if not match:
            continue
        meta: dict[str, str] = {}
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip()] = value.strip()
        feature = meta.get("id")
        if not feature:
            continue
        passed = meta.get("status") == "done"
        for ac in AC_ID.findall(meta.get("ac", "")):
            found.setdefault(f"AC-{ac}", []).append((feature, passed))
    return found


def coverage_state(
    ac: str,
    tests: dict[str, list[str]],
    features: dict[str, list[tuple[str, bool]]],
) -> tuple[str, list[str]]:
    """返回 (missing/partial/covered, 尚未通过的 feature 列表)。"""
    count = len(tests.get(ac, []))
    pending = sorted({feature for feature, passed in features.get(ac, []) if not passed})
    if count == 0:
        return "missing", pending
    if pending:
        return "partial", pending
    return "covered", pending


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
    requirements = [p for p in SPECS.glob("*/requirements.md")]
    if not requirements:
        print("没有找到需求文档")
        return 1

    tests = ac_from_tests()
    # 001/002 已删除；AC-01~29 只保留为历史测试标签，不再进入当前追溯矩阵。
    tests = {ac: files for ac, files in tests.items() if ac not in LEGACY_AC}
    cards = ac_from_cards()
    features = ac_from_features()
    baseline = read_baseline()
    errors: list[str] = []
    rows: list[tuple[str, int, str, str, list[str]]] = []
    partial_count = 0

    for path in sorted(requirements):
        acs = ac_from_requirements(path)
        for ac in acs:
            count = len(tests.get(ac, []))
            card = ",".join(cards.get(ac, [])) or "-"
            state, pending = coverage_state(ac, tests, features)
            rows.append((ac, count, card, state, pending))
            if state == "missing":
                if ac not in baseline:
                    errors.append(f"{ac}：没有测试引用，也不在 scripts/trace-baseline.txt 中")
            elif state == "partial":
                partial_count += 1
                if ac not in baseline:
                    pending_text = "、".join(pending) or "未知 feature"
                    errors.append(
                        f"{ac}：部分覆盖，待 {pending_text} 通过；"
                        "请在 scripts/trace-baseline.txt 登记"
                    )
            elif ac in baseline:
                errors.append(f"{ac}：已有完整测试，基线豁免必须删除")

    known = {row[0] for row in rows}
    for ac in sorted(set(tests) - known):
        errors.append(f"{ac}：测试引用了需求中不存在的验收编号")

    print("AC     测试数  执行卡                 状态")
    for ac, count, card, state, pending in rows:
        if state == "missing":
            flag = "" if ac in baseline else "  <- 缺口"
        elif state == "partial":
            flag = f"  <- 部分覆盖：待 {'、'.join(pending)}"
        else:
            flag = ""
        print(f"{ac}   {count:>4}   {card:<20} {state}{flag}")
    if baseline:
        print("\n已登记基线（缺口/部分覆盖，待承接）：")
        for ac, reason in baseline.items():
            print(f"  {ac}: {reason}")

    if errors:
        print(f"\n追溯检查失败，{len(errors)} 个问题：")
        for item in errors:
            print("  - " + item)
        return 1 if strict else 0

    print(
        f"\n追溯检查通过：{len(rows)} 条 AC，{len(baseline)} 条已登记基线，"
        f"{partial_count} 条部分覆盖。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
