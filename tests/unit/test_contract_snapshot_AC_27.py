"""AC-27：OpenAPI 契约与 R0-2 迁移前快照一致。"""

import json
from pathlib import Path
from typing import Any

from services.api.main import create_app
from services.platform.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "openapi-r0-2.json"


def _first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    if type(expected) is not type(actual):
        return f"{path}: 类型 {type(expected).__name__} != {type(actual).__name__}"
    if isinstance(expected, dict):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing or extra:
            return f"{path}: 缺 {missing}，多 {extra}"
        for key in sorted(expected):
            difference = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}: 长度 {len(expected)} != {len(actual)}"
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            difference = _first_difference(left, right, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if expected != actual:
        return f"{path}: {expected!r} != {actual!r}"
    return None


def test_openapi_matches_r0_2_snapshot_AC_27() -> None:
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    actual = create_app(Settings(environment="test", oms_base_url="")).openapi()

    difference = _first_difference(expected, actual)
    assert difference is None, f"OpenAPI 与快照不一致：{difference}"
