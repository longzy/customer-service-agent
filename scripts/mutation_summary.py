#!/usr/bin/env python3
"""按模块/函数汇总 mutmut 结果，定位测试薄弱点。

输入是 `mutmut results --all true` 的 stdout；`mutation.sh --by-function`
负责把结果管道进来，避免人工逐条 `mutmut show`。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LINE = re.compile(
    r"^(?P<module>backend(?:\.[a-z_]+)+)\.(?P<body>.+)__mutmut_\d+:\s*(?P<status>.+)$"
)


def parse(text: str) -> dict[tuple[str, str], Counter[str]]:
    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for raw in text.splitlines():
        match = LINE.match(raw.strip())
        if match is None:
            continue
        body = match.group("body")
        if "ǁ" in body:
            parts = body.split("ǁ")
            body = ".".join(parts[-2:]) if len(parts) >= 3 else parts[-1]
        label = f"{match.group('module')}.{body}"
        grouped[(match.group("module"), label)][match.group("status").strip()] += 1
    return grouped


def render(
    grouped: dict[tuple[str, str], Counter[str]],
    *,
    module: str | None = None,
    only_gaps: bool = True,
) -> str:
    lines: list[str] = []
    module_totals: Counter[str] = Counter()
    for (owner, label), statuses in sorted(grouped.items()):
        if module is not None and not owner.startswith(module):
            continue
        gaps = statuses["survived"] + statuses["no tests"]
        if only_gaps and gaps == 0:
            continue
        module_totals[owner] += gaps
        detail = f"存活={statuses['survived']} 无测试={statuses['no tests']}"
        lines.append(f"{label:70s} {detail:24s} 缺口={gaps}")
    if not lines:
        return "没有存活/无测试的突变；检查模块名或先运行突变。"
    lines.append("")
    for owner, total in module_totals.most_common():
        lines.append(f"{owner:60s} 缺口合计={total}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按函数汇总 mutmut 缺口")
    parser.add_argument("--module", help="只显示该模块前缀，如 backend.workflows")
    parser.add_argument(
        "--all",
        action="store_true",
        help="同时显示没有缺口的函数（默认只显示存活/无测试）",
    )
    parser.add_argument("--input", help="从文件读取；默认 stdin")
    args = parser.parse_args(argv)

    text = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    if not text.strip():
        print("没有突变结果；先运行 ./scripts/mutation.sh", file=sys.stderr)
        return 1
    print(render(parse(text), module=args.module, only_gaps=not args.all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
