#!/usr/bin/env python3
"""检查 scripts/ 与 .githooks/ 的 shell 脚本语法；本机有 shellcheck 时再跑 lint。"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def shell_for(path: Path) -> str:
    first = path.read_text(encoding="utf-8").splitlines()[0] if path.stat().st_size else ""
    return "bash" if "bash" in first else "sh"


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
    if shellcheck:
        result = subprocess.run(  # noqa: S603 - 固定 shellcheck 与仓库内脚本
            [shellcheck, *[str(path) for path in paths]],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            failures += 1
            print(result.stdout, file=sys.stderr)
    else:
        print("shellcheck 未安装：只做 sh/bash -n 语法检查。")
    if failures:
        return 1
    print(f"shell 检查通过：{len(paths)} 个脚本。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
