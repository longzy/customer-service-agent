"""AC-29：verify 收口与迁移基线清零。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_verify_and_baseline_are_closeout_ready_AC_29() -> None:
    verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    baseline = (ROOT / "scripts" / "import-baseline.txt").read_text(encoding="utf-8")

    assert "check-imports.py --strict" in verify
    prod_import = next(line for line in verify.splitlines() if "--no-dev python" in line)
    assert "ENVIRONMENT=test" in prod_import
    assert "MODEL_API_KEY=''" in prod_import
    effective = [
        line for line in baseline.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    assert effective == []
