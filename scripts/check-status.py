#!/usr/bin/env python3
"""当前状态一致性检查：CURRENT.md ↔ tasks.md ↔ 执行卡。

CURRENT.md 是给人看的一页状态，但它的每个事实都必须能从产物推导出来。
本脚本检查四件事：

1. 状态与事实一致：任务勾选、执行卡状态、CURRENT.md 三处不能互相矛盾。
2. 引用的任务必须存在：CURRENT.md 里出现的 T-XX 必须能在 tasks.md 或执行卡中找到。
3. 未完成任务不能消失：tasks.md 中未勾选的任务必须出现在 CURRENT.md 的进行中/阻塞/下一步。
4. 列表编号连续：手工追加导致 2、2、3、3 的序号重复会被拦下。

用法：python3 scripts/check-status.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "docs" / "CURRENT.md"
SPECS = ROOT / "docs" / "specs"
TASK_FILES = sorted(SPECS.glob("*/tasks.md"))
CARDS = ROOT / "docs" / "tasks"
TASK_ID = re.compile(r"T-?(\d{2})")
PATH_TOKEN = re.compile(r"`([^`\n]+)`")
PATH_PREFIXES = ("docs/", "services/", "packages/", "tests/", "scripts/", "apps/", "migrations/")

errors: list[str] = []


def canonical(task_id: str) -> str:
    return f"T-{task_id}"


def section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def main() -> int:
    text = CURRENT.read_text(encoding="utf-8")
    task_texts = {path: path.read_text(encoding="utf-8") for path in TASK_FILES}

    closed: set[str] = set()
    opened: set[str] = set()
    for tasks_text in task_texts.values():
        for line in tasks_text.splitlines():
            match = re.match(r"- \[([ x])\] T-?(\d{2})\b", line)
            if not match:
                continue
            task = canonical(match.group(2))
            (closed if match.group(1) == "x" else opened).add(task)

    cards: dict[str, str] = {}
    for path in CARDS.rglob("T-*.md"):
        lines = path.read_text(encoding="utf-8").splitlines()
        status_line = next((line for line in lines if line.startswith("- 状态：")), "")
        cards[canonical(path.stem[2:])] = status_line.removeprefix("- 状态：").strip()

    sections = {name: section(text, name) for name in ("已完成", "进行中", "阻塞", "下一步")}
    mentioned: set[str] = set()
    for body in sections.values():
        mentioned |= {canonical(number) for number in TASK_ID.findall(body)}
    known = closed | opened | set(cards)

    for task in sorted(mentioned - known):
        errors.append(f"docs/CURRENT.md：引用了不存在的任务 {task}")

    for task in sorted(closed & set(cards)):
        if not cards[task].startswith("已完成"):
            errors.append(f"{task}：tasks.md 已勾选，但执行卡状态为「{cards[task] or '未声明'}」")
    for task in sorted(set(cards) - closed):
        if cards[task].startswith("已完成"):
            errors.append(f"{task}：执行卡已完成，但 tasks.md 未勾选")

    for task in sorted({canonical(n) for n in TASK_ID.findall(sections["已完成"])}):
        if task not in closed:
            errors.append(f"docs/CURRENT.md：{task} 列在「已完成」，但 tasks.md 未勾选或不存在")
    for task in sorted({canonical(n) for n in TASK_ID.findall(sections["进行中"])}):
        if task in closed:
            errors.append(f"docs/CURRENT.md：{task} 已勾选，不应再列在「进行中」")
    for task in sorted({canonical(n) for n in TASK_ID.findall(sections["下一步"])}):
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
            if not re.match(r"- \[x\] T-?\d{2}\b", line):
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
