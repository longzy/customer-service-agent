"""收口脚本自测：检查前置条件并只做确定性更新（基座豁免）。"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "close_feature.py"
GEN_TASKS = ROOT / "scripts" / "gen_tasks.py"


def make_repo(
    root: Path,
    *,
    with_review: bool = True,
    status: str = "review",
    risk: str = "T2",
    verify_row: str | None = None,
) -> None:
    spec = root / "docs" / "specs" / "001-demo"
    task = root / "docs" / "tasks" / "001-demo"
    review = root / "docs" / "reviews" / "001-demo"
    for path in (spec, task, review):
        path.mkdir(parents=True)
    (spec / "tasks.md").write_text(
        "# demo 任务\n\n- 状态：已批准\n- 依据：`requirements.md`、`design.md`\n",
        encoding="utf-8",
    )
    (task / "F-01.md").write_text(
        "---\n"
        "id: F-01\n"
        "title: demo\n"
        "spec: 001-demo\n"
        "milestone: M1\n"
        f"status: {status}\n"
        "category: functional\n"
        f"risk: {risk}\n"
        "ac: [AC-30]\n"
        "updated: 2026-11-21\n"
        "---\n\n"
        "# 任务执行卡：F-01 demo\n\n"
        "## 4. 证据\n\n```text\npytest 1 passed\n```\n\n"
        "## 6. 完成的定义\n\n- [ ] 证据已填写\n- [ ] STATUS 已更新\n",
        encoding="utf-8",
    )
    if with_review:
        verify_line = f"| 收口全量（回填） | {verify_row} |\n" if verify_row is not None else ""
        (review / "F-01.md").write_text(
            f"# 评审记录\n\n## 0. 门禁复核\n\n{verify_line}\n## 逐 AC\n\n通过\n\n"
            "## 阻断项\n\n无\n\n## 结论\n\n通过\n",
            encoding="utf-8",
        )
    (root / "docs" / "STATUS.md").write_text(
        "# 当前项目状态\n\n## 进行中\n\n- F-01：待评审\n\n## 下一步\n\n1. F-01 收口\n\n"
        "## 已完成\n\n- F-00：demo\n\n## 阻塞\n\n无\n\n## 待确认决策\n\n无\n",
        encoding="utf-8",
    )
    (root / "scripts").mkdir()
    shutil.copy(GEN_TASKS, root / "scripts" / "gen_tasks.py")
    # 收口会先跑仓库内的 trace.py；临时仓库放一个成功桩。
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


def test_状态不是review时阻断_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, status="doing")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "status 不是 review" in result.stderr


def test_apply更新frontmatter并生成tasks_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    status_before = (tmp_path / "docs" / "STATUS.md").read_text(encoding="utf-8")
    result = run(tmp_path, "--apply")
    assert result.returncode == 0, result.stdout + result.stderr

    card = (tmp_path / "docs" / "tasks" / "001-demo" / "F-01.md").read_text(encoding="utf-8")
    assert "status: done" in card
    assert "- [x] 证据已填写" in card
    assert "- [x] STATUS 已更新" in card

    tasks = (tmp_path / "docs" / "specs" / "001-demo" / "tasks.md").read_text(encoding="utf-8")
    assert "| F-01 | demo | AC-30 | 已完成 |" in tasks

    # STATUS 的人工摘要不由脚本猜测
    assert (tmp_path / "docs" / "STATUS.md").read_text(encoding="utf-8") == status_before


def test_已收口时apply不重复_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    first = run(tmp_path, "--apply")
    assert first.returncode == 0, first.stdout + first.stderr
    second = run(tmp_path, "--apply")
    assert second.returncode == 0
    assert "已收口" in second.stdout


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


def test_结论首句通过时历史轮次的不通过不阻断收口_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    review = tmp_path / "docs" / "reviews" / "001-demo" / "F-01.md"
    review.write_text(
        "# 评审记录\n\n## 结论\n\n通过。2 轮：首轮安全轴不通过（1 个阻塞，已关闭）。\n",
        encoding="utf-8",
    )
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "收口检查通过" in result.stdout


def test_T3缺少安全评审时阻断_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, risk="T3")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "T3 缺少 `## 安全评审`" in result.stderr


def test_T3安全评审通过时允许收口_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, risk="T3")
    review = tmp_path / "docs" / "reviews" / "001-demo" / "F-01.md"
    review.write_text(
        review.read_text(encoding="utf-8") + "\n## 安全评审\n\n- 越权矩阵：通过\n- 结论：通过\n",
        encoding="utf-8",
    )
    result = run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_T3安全评审不通过时阻断_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, risk="T3")
    review = tmp_path / "docs" / "reviews" / "001-demo" / "F-01.md"
    review.write_text(
        review.read_text(encoding="utf-8") + "\n## 安全评审\n\n- 结论：不通过\n",
        encoding="utf-8",
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "T3 安全评审结论为「不通过」" in result.stderr


def _git() -> str:
    path = shutil.which("git")
    assert path is not None
    return path


def _init_git(root: Path) -> str:
    git = _git()
    command = [git, "-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run([git, "init", "-q"], cwd=root, check=True)  # noqa: S603
    subprocess.run([*command, "add", "-A"], cwd=root, check=True)  # noqa: S603
    subprocess.run([*command, "commit", "-qm", "init"], cwd=root, check=True)  # noqa: S603
    result = subprocess.run(  # noqa: S603
        [git, "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True
    )
    return result.stdout.strip()


def _shortstat(root: Path, sha: str) -> str:
    result = subprocess.run(  # noqa: S603
        [_git(), "show", "--shortstat", "--format=", sha],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_evidence(root: Path, block: str) -> None:
    card = root / "docs" / "tasks" / "001-demo" / "F-01.md"
    text = card.read_text(encoding="utf-8")
    assert "```text\npytest 1 passed\n```" in text
    card.write_text(text.replace("```text\npytest 1 passed\n```", block), encoding="utf-8")


def test_收口全量未回填时阻断_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, verify_row="待收口 `make verify`")
    result = run(tmp_path)

    assert result.returncode == 1
    assert "收口全量（回填）" in result.stderr


def test_收口全量已回填时通过_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, verify_row="通过：pytest 1 passed")
    result = run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_证据diff统计一致时通过_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    sha = _init_git(tmp_path)
    stat = _shortstat(tmp_path, sha)
    _write_evidence(
        tmp_path,
        f"```text\n$ git show --shortstat --oneline {sha}\n{sha} init\n{stat}\n```",
    )

    result = run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_证据diff统计不一致时阻断_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    sha = _init_git(tmp_path)
    _write_evidence(
        tmp_path,
        f"```text\n$ git show --shortstat --oneline {sha}\n{sha} init\n"
        " 99 files changed, 1 insertion(+) \n```",
    )

    result = run(tmp_path)

    assert result.returncode == 1
    assert "diff 统计" in result.stderr
