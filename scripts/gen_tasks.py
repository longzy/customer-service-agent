#!/usr/bin/env python3
"""从执行卡 frontmatter 生成 spec 的 tasks.md 索引。

状态源只有一处：`docs/tasks/<spec>/F-XX.md` 的 frontmatter。
本脚本只读执行卡，写 `docs/specs/<spec>/tasks.md` 的表格；表格是派生视图。

用法：
    python3 scripts/gen_tasks.py            # 生成全部 spec
    python3 scripts/gen_tasks.py 003-order-query
    python3 scripts/gen_tasks.py --check    # 只比较，不写；有差异退出 1
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "docs" / "specs"
CARDS = ROOT / "docs" / "tasks"

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
STATUS_LABEL = {
    "todo": "未开始",
    "doing": "进行中",
    "review": "待评审",
    "done": "已完成",
    "blocked": "阻塞",
}
TABLE_START = "<!-- gen:start -->"
TABLE_END = "<!-- gen:end -->"


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta


def card_meta(card: Path) -> dict[str, str] | None:
    meta = parse_frontmatter(card.read_text(encoding="utf-8"))
    if not meta.get("id"):
        return None
    return meta


def table_for(spec: str) -> str:
    rows = []
    for card in sorted((CARDS / spec).glob("F-*.md")):
        meta = card_meta(card)
        if meta is None:
            continue
        acs = re.findall(r"AC-\d+", meta.get("ac", ""))
        title = meta.get("title", "")
        if len(title) > 40:
            title = title[:40] + "…"
        status = STATUS_LABEL.get(meta.get("status", "todo"), meta.get("status", "todo"))
        rows.append(
            f"| {meta['id']} | {title} | {'、'.join(acs) or '—'} | {status} "
            f"| [打开](../../tasks/{spec}/{meta['id']}.md) |"
        )
    header = [
        TABLE_START,
        "| ID | 任务 | AC | 状态 | 卡片 |",
        "|---|---|---|---|---|",
        *rows,
        TABLE_END,
    ]
    return "\n".join(header)


def replace_table(text: str, block: str) -> str:
    """替换标记区；没有标记时替换第一个 `| ID |` 表格。"""
    if TABLE_START in text and TABLE_END in text:
        start = text.index(TABLE_START)
        end = text.index(TABLE_END) + len(TABLE_END)
        return text[:start] + block + text[end:]
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("| ID |"))
    except StopIteration:
        return text + "\n" + block + "\n"
    end = start
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    head = "\n".join(lines[:start])
    tail = "\n".join(lines[end:])
    return f"{head}\n{block}\n{tail}"


def generate(spec_dir: Path, check: bool) -> bool:
    spec = spec_dir.name
    tasks = spec_dir / "tasks.md"
    if not tasks.exists():
        print(f"跳过 {spec}：没有 tasks.md", file=sys.stderr)
        return True
    original = tasks.read_text(encoding="utf-8")
    updated = replace_table(original, table_for(spec))
    if updated == original:
        return True
    if check:
        print(f"{tasks}：与执行卡 frontmatter 不一致，请运行 make gen-tasks", file=sys.stderr)
        return False
    tasks.write_text(updated, encoding="utf-8")
    print(f"更新 {tasks}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从执行卡 frontmatter 生成 tasks.md")
    parser.add_argument("spec", nargs="?", help="spec 目录名，如 003-order-query")
    parser.add_argument("--check", action="store_true", help="只比较，不写")
    args = parser.parse_args(argv)

    targets = [SPECS / args.spec] if args.spec else sorted(p for p in SPECS.iterdir() if p.is_dir())
    ok = True
    for spec_dir in targets:
        if not spec_dir.exists():
            print(f"规格目录不存在：{spec_dir}", file=sys.stderr)
            return 2
        ok = generate(spec_dir, args.check) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
