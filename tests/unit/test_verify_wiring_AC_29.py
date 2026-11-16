"""AC-29：verify 收口与迁移基线清零。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_verify_and_baseline_are_closeout_ready_AC_29() -> None:
    verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    baseline = (ROOT / "scripts" / "import-baseline.txt").read_text(encoding="utf-8")

    assert "check-imports.py --strict" in verify
    assert "ENVIRONMENT=test MODEL_API_KEY= uv run --no-dev python" in verify
    effective = [
        line for line in baseline.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    assert effective == []
