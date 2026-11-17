"""AC-28：DB metadata 与 R0-2 迁移前快照一致。"""

import json
from pathlib import Path
from typing import Any

import backend.platform.models  # noqa: F401  显式导入以注册 metadata
from backend.platform.models import Base

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "db-schema-r0-2.json"


def _schema() -> dict[str, Any]:
    schema: dict[str, Any] = {}
    for name, table in sorted(Base.metadata.tables.items()):
        schema[name] = {
            "columns": [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                }
                for column in table.columns
            ],
            "unique_constraints": sorted(
                constraint.name
                for constraint in table.constraints
                if constraint.__class__.__name__ == "UniqueConstraint" and constraint.name
            ),
        }
    return schema


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


def test_db_metadata_matches_r0_2_snapshot_AC_28() -> None:
    actual = _schema()
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert actual, "Base.metadata 为空：未显式导入 models"
    difference = _first_difference(expected, actual)
    assert difference is None, f"DB schema 与快照不一致：{difference}"
