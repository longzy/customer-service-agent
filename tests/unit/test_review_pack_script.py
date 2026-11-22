"""评审包脚本自测：包含 AC 原文、执行卡决策与门禁命令（基座豁免）。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "review_pack.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定脚本路径
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_评审包包含AC原文与评审命令_基座豁免() -> None:
    result = run("F-08", "--base", "HEAD")
    assert result.returncode == 0, result.stderr
    assert "AC-36" in result.stdout
    assert "make review-check" in result.stdout
    assert "make verify-check" in result.stdout
    assert "TEST_DB_NAME=customer_service_review_f_08_std" in result.stdout
    assert "docs/process/review-prompts.md" in result.stdout


def test_评审包包含执行卡与plan_基座豁免() -> None:
    result = run("F-08", "--base", "HEAD")
    assert result.returncode == 0, result.stderr
    assert "## 4. 执行卡：改变范围与任务决策" in result.stdout
    assert "## 5. 设计全文（design.md）" in result.stdout
    assert "领取后接管" in result.stdout


def test_未知feature返回非零_基座豁免() -> None:
    result = run("F-99", "--base", "HEAD")
    assert result.returncode != 0
    assert "找不到执行卡" in result.stderr


def test_固定点可从任务号自动识别_基座豁免() -> None:
    """提交 scope 用 003 时，subject 里的 F-26 仍能推出固定点。"""
    result = run("F-26")
    assert result.returncode == 0, result.stderr
    assert "固定点：" in result.stdout


def test_评审包可包含工作区未提交改动_基座豁免() -> None:
    result = run("F-08", "--base", "HEAD", "--include-worktree")
    assert result.returncode == 0, result.stderr
    assert "含工作区未提交改动" in result.stdout
    assert "完整 diff 用 `git diff HEAD`" in result.stdout
