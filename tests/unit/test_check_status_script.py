"""状态检查器的自测：执行卡 frontmatter 与 STATUS.md 一致（基座豁免）。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-status.py"


def make_repo(
    root: Path,
    *,
    status: str,
    completed: str = "",
    in_progress: str = "",
) -> None:
    (root / "docs" / "specs" / "001-demo").mkdir(parents=True)
    (root / "docs" / "tasks" / "001-demo").mkdir(parents=True)
    (root / "docs" / "specs" / "001-demo" / "tasks.md").write_text(
        "# demo 任务\n\n"
        "| ID | 任务 | AC | 状态 | 卡片 |\n"
        "|---|---|---|---|---|\n"
        "| F-01 | demo | AC-30 | 未开始 | [打开](../../tasks/001-demo/F-01.md) |\n",
        encoding="utf-8",
    )
    (root / "docs" / "tasks" / "001-demo" / "F-01.md").write_text(
        "---\n"
        "id: F-01\n"
        "title: demo\n"
        "spec: 001-demo\n"
        f"status: {status}\n"
        "ac: [AC-30]\n"
        "---\n\n# F-01\n",
        encoding="utf-8",
    )
    (root / "docs" / "STATUS.md").write_text(
        "# 当前项目状态\n\n"
        f"## 已完成\n\n{completed}\n\n"
        f"## 进行中\n\n{in_progress}\n\n"
        "## 阻塞\n\n无\n\n"
        "## 下一步\n\n无\n",
        encoding="utf-8",
    )


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定脚本路径，输入来自 tmp_path
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_已完成任务与卡片一致时通过_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, status="done", completed="- F-01：demo")
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_卡片未完成但写在已完成时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, status="doing", completed="- F-01：demo")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "列在「已完成」，但执行卡不存在或状态不是 done" in result.stdout


def test_已完成任务出现在进行中时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(
        tmp_path,
        status="done",
        completed="- F-01：demo",
        in_progress="- F-01：不应该出现",
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "不应再列在「进行中」" in result.stdout


def test_待评审任务可以留在进行中_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, status="review", in_progress="- F-01：待评审")
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_未完成任务必须出现在进行中或下一步_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, status="doing")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "没有出现在进行中/阻塞/下一步" in result.stdout
