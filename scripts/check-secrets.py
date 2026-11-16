#!/usr/bin/env python3
"""密钥扫描：检查入库文件与暂存区是否含真实密钥。

规则：
- 只扫描 Git 跟踪的文本文件；`.env` 等未跟踪文件不在范围内。
- 命中常见密钥格式即失败，占位符与示例值豁免。
- pre-commit 用 --staged，CI 用默认的全量模式。

用法：
    python3 scripts/check-secrets.py
    python3 scripts/check-secrets.py --staged
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = shutil.which("git") or "git"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("模型或第三方 API 密钥", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("AWS 访问密钥", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub 令牌", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("私钥", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)

# 占位符、示例与文档说明不报
PLACEHOLDER = re.compile(r"(your[-_]|example|placeholder|redacted|<[^>]+>|x{8,})", re.IGNORECASE)

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".pdf",
    ".lock",
    ".pyc",
}
SKIP_PARTS = {"node_modules", ".next", "mutants", ".venv", ".uv-cache", ".pnpm-store", ".git"}
MAX_BYTES = 2 * 1024 * 1024


def scan_text(text: str) -> list[str]:
    """返回命中行，格式为「行号: 类型」。

    只按命中的片段判断占位符：整行豁免会让 `sk-真实密钥 # example` 漏报。
    """
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            match = pattern.search(line)
            if match is None:
                continue
            if PLACEHOLDER.search(match.group(0)):
                continue
            findings.append(f"{number}: {label}")
            break
    return findings


def _candidates(staged: bool) -> list[Path]:
    if staged:
        command = [GIT, "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    else:
        command = [GIT, "ls-files"]
    output = subprocess.run(  # noqa: S603 - 参数固定，无 shell
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / line for line in output.splitlines() if line.strip()]


def _read_text(path: Path, staged: bool) -> str | None:
    """staged 模式读取暂存区内容，避免“add 后再改工作区”绕过扫描。"""
    if staged:
        result = subprocess.run(  # noqa: S603 - 参数固定，无 shell
            [GIT, "show", f":{path.relative_to(ROOT)}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def scan_repository(staged: bool = False) -> list[str]:
    findings: list[str] = []
    for path in _candidates(staged):
        if not path.is_file():
            continue
        if path.suffix.lower() in SKIP_SUFFIXES or SKIP_PARTS & set(path.parts):
            continue
        if path.stat().st_size > MAX_BYTES:
            continue
        text = _read_text(path, staged)
        if text is None:
            continue
        for hit in scan_text(text):
            findings.append(f"{path.relative_to(ROOT)}:{hit}")
    return findings


def main() -> int:
    staged = "--staged" in sys.argv
    findings = scan_repository(staged=staged)
    if findings:
        print(f"疑似密钥，{len(findings)} 处（请改用环境变量并轮换密钥）：")
        for item in findings:
            print("  - " + item)
        return 1
    scope = "暂存区" if staged else "已跟踪文件"
    print(f"密钥扫描通过：{scope}无命中。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
