#!/usr/bin/env python3
"""检查每个 HTTP 路由至少被一个测试引用。"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTE = re.compile(r'@(?:router|app)\.(?:get|post|delete|put|patch)\("([^"]+)"')
PREFIX = re.compile(r'APIRouter\(prefix="([^"]+)"')


def routes() -> list[str]:
    found: list[str] = []
    for path in (ROOT / "services" / "api").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        prefix = PREFIX.search(text)
        base = prefix.group(1) if prefix else ""
        for route in ROUTE.findall(text):
            full = (base + route).replace("//", "/") or "/"
            if full == "":
                full = "/"
            found.append(full)
    return sorted(set(found))


def tests_text() -> str:
    chunks = []
    for path in (ROOT / "tests").rglob("test_*.py"):
        chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def main() -> int:
    text = tests_text()
    missing = [route for route in routes() if route not in text]
    if missing:
        print("以下路由没有测试引用：")
        for route in missing:
            print("  - " + route)
        return 1
    print(f"路由覆盖检查通过：{len(routes())} 个路由均有测试引用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
