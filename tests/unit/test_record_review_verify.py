"""`make verify` 回填评审记录「收口全量」行（基座豁免）。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "record_review_verify.py"


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    task = tmp_path / "docs" / "tasks" / "001-demo"
    review = tmp_path / "docs" / "reviews" / "001-demo"
    task.mkdir(parents=True)
    review.mkdir(parents=True)
    (task / "F-01.md").write_text("---\nid: F-01\n---\n", encoding="utf-8")
    return task, review


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定脚本与仓库内临时路径
        [sys.executable, str(SCRIPT), *args, "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_回填收口全量行_基座豁免(tmp_path: Path) -> None:
    _, review = _repo(tmp_path)
    path = review / "F-01.md"
    path.write_text("# 评审记录\n\n| 收口全量（回填） | 待收口 |\n", encoding="utf-8")

    result = _run(tmp_path, "F-01", "- 最近验证：pytest 1 passed")

    assert result.returncode == 0, result.stderr
    assert "| 收口全量（回填） | pytest 1 passed |" in path.read_text(encoding="utf-8")


def test_缺少回填行时失败_基座豁免(tmp_path: Path) -> None:
    _, review = _repo(tmp_path)
    (review / "F-01.md").write_text("# 评审记录\n", encoding="utf-8")

    result = _run(tmp_path, "F-01", "- 最近验证：pytest 1 passed")

    assert result.returncode == 1
    assert "收口全量" in result.stderr
