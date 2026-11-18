#!/usr/bin/env python3
"""从代码生成 domain.json 的错误码契约片段。

事实源是 `backend.domain.errors` 的 `ErrorCode` 与 `SPECS`；本脚本把同一事实
投影到 `packages/contracts/schemas/domain.json` 的三处：

- `$defs.ErrorCode.enum`
- `$defs.ErrorEnvelope.allOf`（每个错误码的 retryable/visible 条件）
- `x-error-specs`

domain.json 的订单等其它 schema 原样保留。`--check` 只比较不写文件，供
pre-commit 与 verify 使用：改错误码后忘记同步会在提交前失败。

用法：
    uv run python scripts/gen_domain_contract.py
    uv run python scripts/gen_domain_contract.py --check
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.domain.errors import SPECS, ErrorCode  # noqa: E402

OUTPUT = ROOT / "packages" / "contracts" / "schemas" / "domain.json"


def build(document: dict[str, Any]) -> dict[str, Any]:
    """返回只替换错误码相关片段的深拷贝。"""
    updated = json.loads(json.dumps(document, ensure_ascii=False))
    codes = list(ErrorCode)

    updated["$defs"]["ErrorCode"] = {
        "type": "string",
        "enum": [code.value for code in codes],
    }
    updated["$defs"]["ErrorEnvelope"]["allOf"] = [
        {
            "if": {"properties": {"code": {"const": code.value}}, "required": ["code"]},
            "then": {
                "properties": {
                    "retryable": {"const": SPECS[code].retryable},
                    "visible": {"const": SPECS[code].visible},
                }
            },
        }
        for code in codes
    ]
    updated["x-error-specs"] = {
        code.value: {
            "retryable": SPECS[code].retryable,
            "visible": SPECS[code].visible,
        }
        for code in codes
    }
    return updated


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只比较，不写文件")
    args = parser.parse_args()

    document = json.loads(OUTPUT.read_text(encoding="utf-8"))
    rendered = render(build(document))
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != rendered:
            print(
                "domain.json 的错误码契约与代码不同步：请运行 "
                "uv run python scripts/gen_domain_contract.py"
            )
            return 1
        print("domain.json 错误码契约与代码同步")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"已生成 {OUTPUT.relative_to(ROOT)} 的错误码契约")
    return 0


if __name__ == "__main__":
    sys.exit(main())
