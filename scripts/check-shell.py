#!/usr/bin/env python3
"""检查 scripts/ 与 .githooks/ 的 shell 脚本：sh/bash 语法 + shellcheck lint。

shellcheck 由 dev 依赖 `shellcheck-py` 提供，版本随 uv.lock 锁定；缺失即失败，
不降级为"只查语法"，避免本机跳过、CI 报错导致判定分裂。
请用 `uv run python scripts/check-shell.py` 执行。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def shell_for(path: Path) -> str:
    first = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else ""
    return "bash" if "bash" in first else "sh"


def shellcheck_version(executable: str) -> str:
    result = subprocess.run(  # noqa: S603 - 固定 shellcheck 与其版本参数
        [executable, "--version"], capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip()
    return "?"


def main() -> int:
    paths = sorted(
        [
            *ROOT.glob("scripts/*.sh"),
            *ROOT.glob(".githooks/*"),
        ]
    )
    paths = [path for path in paths if path.is_file()]
    failures = 0
    for path in paths:
        shell = shell_for(path)
        result = subprocess.run(  # noqa: S603 - 固定 sh/bash 与仓库内脚本
            [shell, "-n", str(path)], capture_output=True, text=True
        )
        if result.returncode != 0:
            failures += 1
            print(f"语法失败：{path}\n{result.stderr.strip()}", file=sys.stderr)
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        print(
            "缺少 shellcheck：请用 `uv run python scripts/check-shell.py` 执行。"
            "它是 dev 依赖（shellcheck-py），直接用 python3 会拿不到。",
            file=sys.stderr,
        )
        return 1
    result = subprocess.run(  # noqa: S603 - 固定 shellcheck 与仓库内脚本
        [shellcheck, *[str(path) for path in paths]],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        failures += 1
        print(result.stdout, file=sys.stderr)
    if failures:
        return 1
    print(f"shell 检查通过：{len(paths)} 个脚本（shellcheck {shellcheck_version(shellcheck)}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
