#!/usr/bin/env python3
"""生成/校验两类测试快照：DB metadata 与 test 形态 OpenAPI。

`tests/unit/test_db_schema_AC_28.py` 与 `test_contract_snapshot_AC_27.py`
直接读取这两个 fixture；新增表、列或路由响应后，用 `make gen-contracts`
一次刷新，不要手写 JSON。`--check` 只比较，不写文件，供 check-contracts 使用。

用法：
    uv run python scripts/gen_test_fixtures.py
    uv run python scripts/gen_test_fixtures.py --check
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# 与 test-db.sh 一致：测试快照不读开发者 .env，并按 test 形态构造模块级 app。
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("SETTINGS_ENV_FILE", "/dev/null")

DB_SCHEMA_OUTPUT = ROOT / "tests" / "fixtures" / "db-schema-r0-2.json"
OPENAPI_OUTPUT = ROOT / "tests" / "fixtures" / "openapi-r0-2.json"


def db_schema() -> dict[str, Any]:
    import backend.platform.models  # noqa: F401  显式导入以注册 metadata
    from backend.platform.models import Base

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


def openapi_spec() -> dict[str, Any]:
    from backend.api.main import create_app
    from backend.platform.settings import Settings

    return create_app(Settings(environment="test", oms_base_url="")).openapi()


def render(document: Any) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成/校验测试快照")
    parser.add_argument("--check", action="store_true", help="只比较，不写文件")
    args = parser.parse_args()

    outputs = (
        (DB_SCHEMA_OUTPUT, db_schema()),
        (OPENAPI_OUTPUT, openapi_spec()),
    )
    failed = False
    for path, document in outputs:
        expected = render(document)
        relative = path.relative_to(ROOT)
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != expected:
                print(f"{relative} 与代码不一致：请运行 make gen-contracts", file=sys.stderr)
                failed = True
            else:
                print(f"测试快照一致：{relative}")
        else:
            path.write_text(expected, encoding="utf-8")
            print(f"已生成测试快照：{relative}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
