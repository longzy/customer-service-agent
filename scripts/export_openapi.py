#!/usr/bin/env python3
"""导出 FastAPI OpenAPI 到 packages/contracts/openapi.json。

使用 production 形态的 app（test-only 路由不进入契约），但显式给出 dummy
OMS/模型配置，避免启动期配置校验失败。`--check` 只比较，不写文件。

`backend.api.main` 在 import 时会按环境变量构建一次模块级 app；CI 没有 `.env`，
所以这里先把同一组 dummy 值写进环境变量，保证导出不依赖宿主机配置。
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONTRACT_SETTINGS: dict[str, object] = {
    "environment": "production",
    "m1_enabled": True,
    "database_url": "postgresql+asyncpg://unused@127.0.0.1/unused",
    "oms_base_url": "https://oms.example.invalid",
    "model_api_key": "contract-export-only",
}

for _name, _value in CONTRACT_SETTINGS.items():
    os.environ.setdefault(_name.upper(), str(_value))

from backend.api.main import create_app  # noqa: E402
from backend.platform.settings import Settings  # noqa: E402

OUTPUT = ROOT / "packages" / "contracts" / "openapi.json"


def build_spec() -> dict[str, object]:
    return create_app(Settings(**CONTRACT_SETTINGS)).openapi()


def render(spec: dict[str, object]) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验已提交文件是否最新")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    rendered = render(build_spec())
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(
                "OpenAPI 与运行时不一致：请运行 "
                f"python3 scripts/export_openapi.py 更新 {args.output}"
            )
            return 1
        print(f"OpenAPI 契约一致：{args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"已导出 OpenAPI：{args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
