#!/usr/bin/env python3
"""门禁反馈指标：评审结论、T3 安全覆盖、最近评测与后续项。

只读仓库事实，不执行测试；用于 `docs/process/feedback.md` 的月度/每 feature 复盘。
用法：
    python3 scripts/gate_metrics.py
    python3 scripts/gate_metrics.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
CONCLUSION = re.compile(r"^## 结论\s*$", re.M)
VERDICT = re.compile(r"^(通过|有条件通过|不通过)")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta


def verdict(text: str) -> str | None:
    match = CONCLUSION.search(text)
    if match is None:
        return None
    for line in text[match.end() :].splitlines():
        stripped = line.strip().lstrip("*_ ").rstrip("*_ ")
        if stripped:
            found = VERDICT.match(stripped)
            return found.group(1) if found else None
    return None


def t3_cards(root: Path) -> list[str]:
    return [
        path.stem
        for path in sorted((root / "docs" / "tasks").glob("*/*.md"))
        if frontmatter(read(path)).get("risk") == "T3"
    ]


def review_stats(root: Path) -> dict[str, object]:
    verdicts: Counter[str] = Counter()
    followups = 0
    security = 0
    for path in sorted((root / "docs" / "reviews").glob("*/F-*.md")):
        text = read(path)
        found = verdict(text)
        if found:
            verdicts[found] += 1
        followups += text.count("接受为后续")
        if "## 安全评审" in text and "结论：通过" in text:
            security += 1
    t3 = t3_cards(root)
    return {
        "reviews": sum(verdicts.values()),
        "verdicts": dict(verdicts),
        "t3_cards": len(t3),
        "t3_security_passed": security,
        "followups": followups,
    }


def latest_eval(root: Path) -> dict[str, object] | None:
    path = root / "evals" / "reports" / "latest.json"
    if not path.exists():
        return None
    document = json.loads(read(path))
    totals = document.get("totals", {})
    coverage = document.get("ac_coverage", {})
    return {
        "ok": document.get("ok"),
        "tests": totals.get("tests"),
        "passed": totals.get("passed"),
        "failed": totals.get("failed"),
        "skipped": totals.get("skipped"),
        "ac_covered": coverage.get("covered"),
        "ac_total": coverage.get("total"),
        "ac_pending": coverage.get("pending"),
    }


def collect(root: Path) -> dict[str, object]:
    return {"reviews": review_stats(root), "latest_eval": latest_eval(root)}


def render(data: dict[str, object]) -> str:
    reviews = data["reviews"]
    lines = [
        "# 门禁反馈指标",
        "",
        f"- 评审记录：{reviews['reviews']}；结论分布：{reviews['verdicts']}",
        f"- T3 安全评审通过：{reviews['t3_security_passed']}/{reviews['t3_cards']}",
        f"- 「接受为后续」出现次数：{reviews['followups']}（需有承接 feature）",
    ]
    latest = data["latest_eval"]
    if latest is None:
        lines.append("- 最近评测：无报告（先跑 `make verify` 或 `./scripts/eval.sh`）")
    else:
        lines.append(
            "- 最近评测："
            f"ok={latest['ok']} tests={latest['tests']} passed={latest['passed']} "
            f"failed={latest['failed']} skipped={latest['skipped']}；"
            f"AC {latest['ac_covered']}/{latest['ac_total']}（待开工 {latest['ac_pending']}）"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="门禁反馈指标")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = collect(args.root)
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
