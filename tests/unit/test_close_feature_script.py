"""收口脚本自测：检查前置条件并只做确定性更新（基座豁免）。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "close_feature.py"


def make_repo(root: Path, *, with_review: bool = True) -> None:
    spec = root / "docs" / "specs" / "001-demo"
    task = root / "docs" / "tasks" / "001-demo"
    review = root / "docs" / "reviews" / "001-demo"
    for path in (spec, task, review):
        path.mkdir(parents=True)
    (spec / "features.md").write_text(
        "| ID | Category | Description | Steps | AC | Passes | Evidence |\n"
        "|---|---|---|---|---|---|---|\n"
        "| F-01 | functional | demo | pytest | AC-30 | false | — |\n",
        encoding="utf-8",
    )
    (task / "F-01.md").write_text(
        "# 任务执行卡：F-01 demo\n\n"
        "- 状态：待评审\n\n"
        "## 4. 证据\n\n```text\npytest 1 passed\n```\n\n"
        "## 6. 完成的定义\n\n- [ ] 证据已填写\n- [ ] CURRENT 已更新\n",
        encoding="utf-8",
    )
    if with_review:
        (review / "F-01.md").write_text(
            "# 评审记录\n\n## 0. 门禁复核\n\n通过\n\n## 逐 AC\n\n通过\n\n"
            "## 阻断项\n\n无\n\n## 结论\n\n通过\n",
            encoding="utf-8",
        )
    (root / "docs" / "CURRENT.md").write_text(
        "# 当前项目状态\n\n## 进行中\n\n- F-01：待评审\n\n## 下一步\n\n1. F-01 收口\n\n"
        "## 已完成\n\n- F-00：demo\n\n## 阻塞\n\n无\n\n## 待确认决策\n\n无\n",
        encoding="utf-8",
    )
    # 收口会先跑仓库内的 trace.py；临时仓库放一个成功桩。
    (root / "scripts").mkdir()
    (root / "scripts" / "trace.py").write_text("import sys\n\nsys.exit(0)\n", encoding="utf-8")


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定脚本路径，输入来自 tmp_path
        [sys.executable, str(SCRIPT), "F-01", "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_收口检查通过_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "收口检查通过" in result.stdout


def test_缺少评审记录时阻断_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, with_review=False)
    result = run(tmp_path)
    assert result.returncode == 1
    assert "评审记录不存在" in result.stderr


def test_apply只更新features与执行卡_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    current_before = (tmp_path / "docs" / "CURRENT.md").read_text(encoding="utf-8")
    result = run(tmp_path, "--apply", "--evidence", "2026-11-18：pytest 1 passed")
    assert result.returncode == 0, result.stdout + result.stderr

    features = (tmp_path / "docs" / "specs" / "001-demo" / "features.md").read_text(
        encoding="utf-8"
    )
    assert (
        "| F-01 | functional | demo | pytest | AC-30 | true | 2026-11-18：pytest 1 passed |"
        in features
    )
    card = (tmp_path / "docs" / "tasks" / "001-demo" / "F-01.md").read_text(encoding="utf-8")
    assert "- 状态：已完成" in card
    assert "- [x] 证据已填写" in card
    assert "- [x] CURRENT 已更新" in card
    # CURRENT 的人工摘要不由脚本猜测
    assert (tmp_path / "docs" / "CURRENT.md").read_text(encoding="utf-8") == current_before


def test_证据含竖线时拒绝_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    result = run(tmp_path, "--apply", "--evidence", "a | b")
    assert result.returncode == 1
    assert "不含 `|`" in result.stderr


def test_已收口时apply不覆盖证据_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    first = run(tmp_path, "--apply", "--evidence", "2026-11-18：pytest 1 passed")
    assert first.returncode == 0, first.stdout + first.stderr
    evidence = "2026-11-18：pytest 1 passed"
    second = run(tmp_path, "--apply", "--evidence", "不应覆盖")
    assert second.returncode == 0
    assert "已收口" in second.stdout
    features = (tmp_path / "docs" / "specs" / "001-demo" / "features.md").read_text(
        encoding="utf-8"
    )
    assert evidence in features
    assert "不应覆盖" not in features


def test_trace失败时阻断收口_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    (tmp_path / "scripts" / "trace.py").write_text(
        "import sys\n\nprint('过期基线')\nsys.exit(1)\n",
        encoding="utf-8",
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "trace.py --strict 未通过" in result.stderr
    assert "过期基线" in result.stderr
