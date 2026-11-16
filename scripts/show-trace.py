#!/usr/bin/env python3
"""开发期 trace 查询：按 trace_id + tenant_id 输出完整链路。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.api.db import session_factory
from services.api.observability import load_trace


async def run(trace_id: str, tenant_id: str) -> dict[str, object]:
    async with session_factory() as session:
        view = await load_trace(session, trace_id, tenant_id)
        return view.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description="按 trace_id 查询执行链路")
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    args = parser.parse_args()
    payload = asyncio.run(run(args.trace_id, args.tenant_id))
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 1 if not payload["events"] and payload["cancellation"] is None else 0


if __name__ == "__main__":
    sys.exit(main())
