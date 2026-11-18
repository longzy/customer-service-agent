#!/usr/bin/env python3
"""feature 收口检查与机械更新。

只做两件确定性的事：
1. 检查收口前置条件（评审通过、执行卡证据、CURRENT 状态一致）；
2. `--apply` 时更新 features 的 Passes/Evidence 与执行卡状态/勾选。

CURRENT.md 的人工摘要仍由人写：脚本只检查并打印剩余步骤，不猜摘要。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FEATURE_ROW = re.compile(r"^\| (F-\d{2}) \|")
STATUS_LINE = re.compile(r"^- 状态：(.+)$", re.M)
CHECKBOX = re.compile(r"^- \[ \] ", re.M)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def find_feature(specs_root: Path, feature: str) -> tuple[Path, list[str]] | None:
    for path in sorted(specs_root.glob("*/features.md")):
        lines = read(path).splitlines()
        for line in lines:
            match = FEATURE_ROW.match(line)
            if match and match.group(1) == feature:
                return path, [cell.strip() for cell in line.strip().strip("|").split("|")]
    return None


def already_closed(root: Path, feature: str) -> bool:
    """features Passes=true 且执行卡已完成为已收口，脚本不应再写。"""
    found = find_feature(root / "docs" / "specs", feature)
    if found is None:
        return False
    features_path, cells = found
    if len(cells) != 7 or cells[5] != "true":
        return False
    card = root / "docs" / "tasks" / features_path.parent.name / f"{feature}.md"
    status = STATUS_LINE.search(read(card)) if card.exists() else None
    return bool(status and status.group(1).strip() == "已完成")


def current_sections(path: Path) -> dict[str, str]:
    text = read(path)
    return {name: section(text, name) for name in ("已完成", "进行中", "阻塞", "下一步")}


def check(root: Path, feature: str) -> list[str]:
    """返回阻断收口的问题；空列表表示可以收口。"""
    problems: list[str] = []
    found = find_feature(root / "docs" / "specs", feature)
    if found is None:
        return [f"{feature}：在 docs/specs/*/features.md 中找不到对应行"]
    features_path, cells = found
    spec_name = features_path.parent.name
    card_path = root / "docs" / "tasks" / spec_name / f"{feature}.md"
    review_path = root / "docs" / "reviews" / spec_name / f"{feature}.md"

    if len(cells) != 7:
        problems.append(f"{features_path}：{feature} 行不是 7 列")
        return problems
    if cells[5] != "false" or cells[6] != "—":
        card_text = read(card_path) if card_path.exists() else ""
        status_match = STATUS_LINE.search(card_text)
        if cells[5] == "true" and status_match and status_match.group(1).strip() == "已完成":
            return []
        problems.append(f"{features_path}：{feature} 的 Passes/Evidence 不是待收口状态")

    if not card_path.exists():
        problems.append(f"{card_path}：执行卡不存在")
    else:
        card = read(card_path)
        if "待评审" not in (STATUS_LINE.search(card).group(1) if STATUS_LINE.search(card) else ""):
            problems.append(f"{card_path}：状态不是 待评审")
        evidence = section(card, "4. 证据")
        if "```" not in evidence:
            problems.append(f"{card_path}：第 4 节证据缺少命令输出代码块")

    if not review_path.exists():
        problems.append(f"{review_path}：评审记录不存在")
    else:
        review = read(review_path)
        conclusion = section(review, "结论")
        if "不通过" in conclusion:
            problems.append(f"{review_path}：结论为不通过")
        elif "通过" not in conclusion:
            problems.append(f"{review_path}：结论未写明通过")

    current = current_sections(root / "docs" / "CURRENT.md")
    pattern = re.compile(rf"\b{re.escape(feature)}\b")
    if pattern.search(current["已完成"]):
        problems.append("docs/CURRENT.md：已在「已完成」，无需重复收口")
    if not (pattern.search(current["进行中"]) or pattern.search(current["下一步"])):
        problems.append("docs/CURRENT.md：未出现在「进行中」或「下一步」")
    return problems


def apply(root: Path, feature: str, evidence: str) -> list[str]:
    problems = check(root, feature)
    if problems:
        return problems
    if "\n" in evidence or "|" in evidence or not evidence.strip():
        return ["--evidence 必须是单行、非空、不含 `|` 的文本"]

    found = find_feature(root / "docs" / "specs", feature)
    if found is None:
        return [f"{feature}：在 docs/specs/*/features.md 中找不到对应行"]
    features_path, cells = found
    spec_name = features_path.parent.name
    features_text = read(features_path)
    old_row = "| " + " | ".join(cells) + " |"
    if old_row not in features_text:
        return [f"{features_path}：无法定位 {feature} 原行，请手工收口"]
    cells[5] = "true"
    cells[6] = evidence.strip()
    features_text = features_text.replace(old_row, "| " + " | ".join(cells) + " |", 1)
    features_path.write_text(features_text, encoding="utf-8")

    card_path = root / "docs" / "tasks" / spec_name / f"{feature}.md"
    card = read(card_path)
    card = STATUS_LINE.sub("- 状态：已完成", card, count=1)
    completion = section(card, "6. 完成的定义")
    card = card.replace(completion, CHECKBOX.sub("- [x] ", completion), 1)
    card_path.write_text(card, encoding="utf-8")
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="feature 收口检查/机械更新")
    parser.add_argument("feature", help="feature 编号，如 F-06")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="只检查，不写文件（默认）")
    parser.add_argument("--apply", action="store_true", help="更新 features 与执行卡")
    parser.add_argument("--evidence", default="", help="写入 features 的单行证据")
    args = parser.parse_args()

    if not re.fullmatch(r"F-\d{2}", args.feature):
        print(f"feature 编号不合法：{args.feature}", file=sys.stderr)
        return 2

    root = args.root.resolve()
    if args.apply:
        if already_closed(root, args.feature):
            print(f"{args.feature}：已收口，无需修改。")
            return 0
        problems = apply(root, args.feature, args.evidence)
        if problems:
            print(f"{args.feature} 不能收口：", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"{args.feature}：已更新 features 与执行卡。")
        print("剩余手工步骤：")
        print("  1. 更新 docs/CURRENT.md：从「进行中」「下一步」移除该 feature，")
        print("     并在「已完成」追加一行；")
        print("  2. 运行 make verify；")
        print(f"  3. 提交 docs({args.feature}): 收口状态与证据。")
        return 0

    if already_closed(root, args.feature):
        print(f"{args.feature}：已收口，无需检查。")
        return 0
    problems = check(root, args.feature)
    if problems:
        print(f"{args.feature} 尚未满足收口条件：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"{args.feature} 收口检查通过。")
    print("下一步：")
    print(f"  python3 scripts/close_feature.py {args.feature} --apply --evidence '<单行证据>'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
