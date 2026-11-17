"""状态检查器的自测：F-xx / Passes / CURRENT 三处一致（基座豁免）。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-status.py"


def make_repo(
    root: Path,
    *,
    passes: str,
    card_status: str,
    completed: str = "",
    in_progress: str = "",
) -> None:
    (root / "docs" / "specs" / "001-demo").mkdir(parents=True)
    (root / "docs" / "tasks" / "001-demo").mkdir(parents=True)
    (root / "docs" / "specs" / "001-demo" / "features.md").write_text(
        "| ID | Category | Description | Steps | AC | Passes | Evidence |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| F-01 | functional | demo | pytest | AC-30 | {passes} | evidence |\n",
        encoding="utf-8",
    )
    (root / "docs" / "tasks" / "001-demo" / "F-01.md").write_text(
        f"# F-01\n\n- 状态：{card_status}\n", encoding="utf-8"
    )
    (root / "docs" / "CURRENT.md").write_text(
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


def test_已完成feature与卡片一致时通过_基座豁免(tmp_path: Path) -> None:
    make_repo(
        tmp_path,
        passes="true",
        card_status="已完成",
        completed="- F-01：demo",
    )
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_卡片已完成但Passes为false时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, passes="false", card_status="已完成", completed="- F-01：demo")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "features Passes 未置 true" in result.stdout


def test_已完成ID出现在进行中时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(
        tmp_path,
        passes="true",
        card_status="已完成",
        completed="- F-01：demo",
        in_progress="- F-01：不应该出现",
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "不应再列在「进行中」" in result.stdout


def test_待评审卡片可以留在进行中_基座豁免(tmp_path: Path) -> None:
    make_repo(
        tmp_path,
        passes="true",
        card_status="待评审",
        in_progress="- F-01：待评审",
    )
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
