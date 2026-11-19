#!/usr/bin/env python3
"""可观测数据清理：默认 dry-run，`--apply` 才删除 L3/L3.5；审计只报告。"""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.platform.db import session_factory
from backend.platform.retention import cleanup
from backend.platform.settings import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="清理过期 trace / AI 事件（审计只报告）")
    parser.add_argument("--apply", action="store_true", help="实际删除；默认只 dry-run")
    args = parser.parse_args()
    report = asyncio.run(
        cleanup(
            session_factory,
            apply=args.apply,
            trace_retention_days=settings.trace_retention_days,
            trace_error_retention_days=settings.trace_error_retention_days,
            ai_retention_days=settings.ai_event_retention_days,
            ai_critical_retention_days=settings.ai_event_critical_retention_days,
            audit_retention_days=settings.audit_retention_days,
        )
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
