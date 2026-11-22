#!/usr/bin/env python3
"""全量验证的代码指纹与结果缓存。

`verify.sh --reuse` 用它判断“代码输入是否变化”：未变化时只重跑快检查，
复用上次 pytest/评测/前端结果，避免收口阶段重复 ~3 分钟的全量。
文档正文与任务卡故意不参与指纹；`docs/design-system` 例外，因为单测会读它。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT / ".verify" / "last-full.json"
# 顺序无关；git pathspec 会忽略不存在或未跟踪的目录。
CODE_PATHS = (
    "backend",
    "packages",
    "apps",
    "tests",
    "migrations",
    "scripts",
    "evals",
    "docs/design-system",
    "pyproject.toml",
    "uv.lock",
    "alembic.ini",
    "Makefile",
    ".githooks",
)


def fingerprint(root: Path = ROOT) -> str:
    """对会影响验证结果的源码/测试/配置做内容哈希；忽略文档与生成物。"""
    listed = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z", "-co", "--exclude-standard", "--", *CODE_PATHS],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = sorted(item for item in listed.stdout.decode().split("\0") if item)
    digest = hashlib.sha256()
    for relative in paths:
        path = root / relative
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load(path: Path = DEFAULT_STATE) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def matches(path: Path = DEFAULT_STATE, root: Path = ROOT) -> bool:
    state = load(path)
    return bool(state) and state.get("fingerprint") == fingerprint(root)


def save(
    *,
    pytest_line: str,
    eval_status: int,
    path: Path = DEFAULT_STATE,
    root: Path = ROOT,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint(root),
                "pytest_line": pytest_line,
                "eval_status": eval_status,
                "saved_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=ROOT)
    common.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser = argparse.ArgumentParser(description="全量验证指纹与结果缓存")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("fingerprint", parents=[common], help="打印当前代码指纹")
    sub.add_parser("check", parents=[common], help="指纹与上次成功一致时 exit 0")
    get = sub.add_parser("get", parents=[common], help="读取上次结果字段")
    get.add_argument("--field", required=True)
    save_parser = sub.add_parser("save", parents=[common], help="保存本次成功结果")
    save_parser.add_argument("--pytest-line", required=True)
    save_parser.add_argument("--eval-status", type=int, default=0)

    args = parser.parse_args(argv)
    root = args.root
    state = args.state
    if args.action == "fingerprint":
        print(fingerprint(root))
        return 0
    if args.action == "check":
        if not matches(state, root):
            print("代码输入已变化，需要全量验证", file=sys.stderr)
            return 1
        return 0
    if args.action == "get":
        document = load(state)
        if document is None or args.field not in document:
            print(f"没有可复用的验证结果：{state}", file=sys.stderr)
            return 1
        print(document[args.field])
        return 0
    save(
        pytest_line=args.pytest_line,
        eval_status=args.eval_status,
        path=state,
        root=root,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
