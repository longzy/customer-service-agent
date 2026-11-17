#!/usr/bin/env python3
"""当前状态一致性检查：CURRENT.md ↔ features.md ↔ 执行卡。

CURRENT.md 是给人看的一页状态，但它的每个事实都必须能从产物推导出来。
本脚本检查四件事：

1. 状态与事实一致：执行卡状态、features 的 `Passes`、CURRENT.md 三处不能互相矛盾。
2. 引用的任务必须存在：CURRENT.md 里出现的 F-XX（或历史 T-XX）必须能在执行卡中找到。
3. 未完成任务不能消失：未完成的执行卡必须出现在 CURRENT.md 的进行中/阻塞/下一步。
4. 列表编号连续：手工追加导致 2、2、3、3 的序号重复会被拦下。
5. 任务号全局唯一：同一 F-XX/T-XX 不允许跨规格或重复出现。

用法：python3 scripts/check-status.py
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "docs" / "CURRENT.md"
SPECS = ROOT / "docs" / "specs"
TASK_FILES: list[Path] = []
CARDS = ROOT / "docs" / "tasks"
TASK_ID = re.compile(r"\b([TF])-(\d{2})\b")
CARD_FILE = re.compile(r"^[TF]-\d{2}\.md$")
CHECKBOX = re.compile(r"- \[([ x])\] (T-\d{2})\b")
FEATURE_ROW = re.compile(r"^\| (F-\d{2}) \|")
PATH_TOKEN = re.compile(r"`([^`\n]+)`")
PATH_PREFIXES = ("docs/", "backend/", "packages/", "tests/", "scripts/", "apps/", "migrations/")

errors: list[str] = []


def configure(root: Path) -> None:
    """允许测试用临时仓库根目录运行，不依赖调用点位置。"""
    global ROOT, CURRENT, SPECS, TASK_FILES, CARDS
    ROOT = root.resolve()
    CURRENT = ROOT / "docs" / "CURRENT.md"
    SPECS = ROOT / "docs" / "specs"
    TASK_FILES = sorted(SPECS.glob("*/tasks.md")) + sorted(SPECS.glob("*/features.md"))
    CARDS = ROOT / "docs" / "tasks"


def card_paths() -> list[Path]:
    return sorted(path for path in CARDS.rglob("*.md") if CARD_FILE.match(path.name))


def section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def check_duplicate_task_ids() -> None:
    """任务号全局唯一；同号会静默覆盖 cards 字典，必须显式报错。"""
    task_occurrences: dict[str, list[str]] = {}
    card_occurrences: dict[str, list[str]] = {}
    for path in TASK_FILES:
        relative = path.relative_to(ROOT).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            match = CHECKBOX.match(line)
            if match:
                task_occurrences.setdefault(match.group(2), []).append(relative)
    for path in card_paths():
        card_occurrences.setdefault(path.stem, []).append(path.relative_to(ROOT).as_posix())
    duplicated: set[str] = set()
    for label, occurrences in (
        ("tasks.md", task_occurrences),
        ("执行卡", card_occurrences),
    ):
        for task, paths in sorted(occurrences.items()):
            if len(paths) > 1:
                errors.append(f"{task}：{label} 重复出现（{'、'.join(paths)}）")
                duplicated.add(task)
    specs: dict[str, set[str]] = {}
    for task, paths in task_occurrences.items():
        specs.setdefault(task, set()).update(Path(path).parent.name for path in paths)
    for task, paths in card_occurrences.items():
        specs.setdefault(task, set()).update(Path(path).parent.name for path in paths)
    for task, names in sorted(specs.items()):
        if len(names) > 1 and task not in duplicated:
            errors.append(f"{task}：跨规格重复使用（{'、'.join(sorted(names))}）")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    configure(args.root)
    text = CURRENT.read_text(encoding="utf-8")
    task_texts = {path: path.read_text(encoding="utf-8") for path in TASK_FILES}
    check_duplicate_task_ids()

    closed: set[str] = set()
    opened: set[str] = set()
    passed_features: set[str] = set()
    feature_ids: set[str] = set()
    for tasks_text in task_texts.values():
        for line in tasks_text.splitlines():
            match = CHECKBOX.match(line)
            if match:
                (closed if match.group(1) == "x" else opened).add(match.group(2))
                continue
            feature = FEATURE_ROW.match(line)
            if not feature:
                continue
            feature_ids.add(feature.group(1))
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 7 and cells[5] == "true":
                passed_features.add(feature.group(1))

    cards: dict[str, str] = {}
    for path in card_paths():
        lines = path.read_text(encoding="utf-8").splitlines()
        status_line = next((line for line in lines if line.startswith("- 状态：")), "")
        cards[path.stem] = status_line.removeprefix("- 状态：").strip()
    for card, status in cards.items():
        if not status.startswith("已完成"):
            opened.add(card)
        elif card in passed_features:
            closed.add(card)

    sections = {name: section(text, name) for name in ("已完成", "进行中", "阻塞", "下一步")}
    mentioned = {match.group(0) for body in sections.values() for match in TASK_ID.finditer(body)}
    known = closed | opened | set(cards) | feature_ids

    for task in sorted(mentioned - known):
        errors.append(f"docs/CURRENT.md：引用了不存在的任务 {task}")

    for task in sorted(passed_features - set(cards)):
        errors.append(f"{task}：features Passes=true，但没有执行卡")
    for task in sorted(set(cards) - closed):
        if cards[task].startswith("已完成"):
            errors.append(f"{task}：执行卡已完成，但 tasks.md 未勾选或 features Passes 未置 true")

    for task in sorted({match.group(0) for match in TASK_ID.finditer(sections["已完成"])}):
        if task not in closed:
            errors.append(f"docs/CURRENT.md：{task} 列在「已完成」，但 tasks.md 未勾选或不存在")
    for task in sorted({match.group(0) for match in TASK_ID.finditer(sections["进行中"])}):
        if task in closed:
            errors.append(f"docs/CURRENT.md：{task} 已勾选，不应再列在「进行中」")
    for task in sorted({match.group(0) for match in TASK_ID.finditer(sections["下一步"])}):
        if task in closed:
            errors.append(f"docs/CURRENT.md：{task} 已完成，不应出现在「下一步」")

    for task in sorted(opened - mentioned):
        errors.append(f"docs/CURRENT.md：未完成任务 {task} 没有出现在进行中/阻塞/下一步")

    for name, body in sections.items():
        numbers = [int(n) for n in re.findall(r"^(\d+)\. ", body, re.M)]
        expected = list(range(1, len(numbers) + 1))
        if numbers and numbers != expected:
            errors.append(f"docs/CURRENT.md：{name} 的列表编号不连续 {numbers}")

    for path, tasks_text in task_texts.items():
        for line in tasks_text.splitlines():
            if not re.match(r"- \[x\] T-\d{2}\b", line):
                continue
            for token in PATH_TOKEN.findall(line):
                if not token.startswith(PATH_PREFIXES):
                    continue
                if "<" in token or "*" in token:
                    continue
                if not (ROOT / token.rstrip("/")).exists():
                    errors.append(
                        f"{path.relative_to(ROOT).as_posix()}：已完成任务引用的路径不存在 {token}"
                    )

    if errors:
        print(f"状态一致性检查失败，{len(errors)} 个问题：")
        for item in errors:
            print("  - " + item)
        return 1

    print(
        f"状态一致性检查通过：{len(closed)} 个已完成任务、{len(opened)} 个未完成任务、"
        f"{len(cards)} 张执行卡与 CURRENT.md 对齐。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
