"""OpenAPI 片段必须由 Tool 契约生成，且与契约保持同步（AC-04）。"""

import json
from pathlib import Path

from scripts.gen_tool_openapi import build

OPENAPI = Path("packages/contracts/tools/openapi.json")


def test_openapi片段与契约同步_AC_04() -> None:
    expected = build()
    actual = json.loads(OPENAPI.read_text(encoding="utf-8"))
    assert actual == expected


def test_openapi包含全部Tool_AC_04() -> None:
    doc = build()
    assert set(doc["paths"]) == {
        "/tools/list_recent_orders",
        "/tools/get_order",
        "/tools/get_cancel_eligibility",
        "/tools/submit_cancel",
        "/tools/get_cancel_result",
    }
    assert "ErrorEnvelope" in doc["components"]["schemas"]
