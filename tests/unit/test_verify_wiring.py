"""边界门禁接入 verify.sh 的回归测试（不新增 AC）。"""

import subprocess
import sys
from pathlib import Path


def test_verify_runs_import_boundary_check() -> None:
    text = Path("scripts/verify.sh").read_text(encoding="utf-8")

    assert "check-imports.py --strict" in text


def test_import_boundary_check_passes_on_repository() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check-imports.py", "--strict"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_verify_runs_review_prereqs_check() -> None:
    text = Path("scripts/verify.sh").read_text(encoding="utf-8")

    assert "check-review-prereqs.py" in text


def test_process_commands_are_wired() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    for target in ("verify-changed:", "review-check:", "review-pack:"):
        assert target in makefile
    assert "check-review-prereqs.py" in Path(".githooks/pre-commit").read_text(encoding="utf-8")
