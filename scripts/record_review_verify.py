#!/usr/bin/env python3
"""把 `make verify` 的全量结果回填到评审记录的门禁表。

- 只改 `| 收口全量（回填） | ... |` 这一行，其余内容不动；
- 找不到评审记录或该行时返回非 0，由调用方决定是否告警/阻断。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROW = re.compile(r"^\|\s*收口全量（回填）\s*\|.*\|\s*$", re.M)


def review_path(root: Path, feature: str) -> Path | None:
    for card in sorted((root / "docs" / "tasks").glob("*/F-*.md")):
        if card.stem == feature:
            return root / "docs" / "reviews" / card.parent.name / f"{feature}.md"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="回填评审记录的收口全量结果")
    parser.add_argument("feature", help="feature 编号，如 F-33")
    parser.add_argument("summary", help="verify.sh 生成的验证摘要行")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()

    path = review_path(args.root, args.feature)
    if path is None or not path.exists():
        print(f"回填失败：找不到 {args.feature} 的评审记录", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    if not ROW.search(text):
        print(f"回填失败：{path} 没有「收口全量（回填）」行", file=sys.stderr)
        return 1
    summary = args.summary.removeprefix("- 最近验证：").strip()
    path.write_text(
        ROW.sub(f"| 收口全量（回填） | {summary} |", text, count=1),
        encoding="utf-8",
    )
    print(f"已回填 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
