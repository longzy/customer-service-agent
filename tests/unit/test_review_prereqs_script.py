"""评审前置检查器自测：组件命名、trace 基线归属、CURRENT 评审声称（基座豁免）。"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-review-prereqs.py"


def card_text(fid: str, ac: str) -> str:
    return (
        "---\n"
        f"id: {fid}\n"
        "title: demo\n"
        "spec: 001-demo\n"
        "status: doing\n"
        f"ac: [{ac}]\n"
        "---\n\n"
        f"# 任务执行卡：{fid} demo\n"
    )


def make_repo(root: Path, *, with_review: bool = True, conclusion: str = "通过") -> None:
    for path in (
        root / "docs" / "specs" / "001-demo",
        root / "docs" / "tasks" / "001-demo",
        root / "docs" / "reviews" / "001-demo",
        root / "scripts",
        root / "apps" / "chat" / "features" / "demo" / "components",
        root / "apps" / "chat" / "features" / "demo" / "hooks",
    ):
        path.mkdir(parents=True, exist_ok=True)
    (root / "docs" / "specs" / "001-demo" / "tasks.md").write_text(
        "# demo 任务\n\n- 状态：已批准\n", encoding="utf-8"
    )
    (root / "docs" / "tasks" / "001-demo" / "F-01.md").write_text(
        card_text("F-01", "AC-30"), encoding="utf-8"
    )
    (root / "docs" / "tasks" / "001-demo" / "F-02.md").write_text(
        card_text("F-02", "AC-31"), encoding="utf-8"
    )
    component = root / "apps" / "chat" / "features" / "demo" / "components" / "Foo.tsx"
    component.write_text("export function Foo() {\n  return null;\n}\n", encoding="utf-8")
    hook = root / "apps" / "chat" / "features" / "demo" / "hooks" / "useDemo.ts"
    hook.write_text("export function useDemo() {\n  return null;\n}\n", encoding="utf-8")
    (root / "scripts" / "frontend-structure-baseline.txt").write_text("", encoding="utf-8")
    (root / "scripts" / "trace-baseline.txt").write_text("", encoding="utf-8")
    (root / "docs" / "STATUS.md").write_text(
        "# 当前项目状态\n\n## 进行中\n\n- F-01：评审通过（待收口）\n\n"
        "## 已完成\n\n## 下一步\n\n## 阻塞\n\n无\n",
        encoding="utf-8",
    )
    if with_review:
        (root / "docs" / "reviews" / "001-demo" / "F-01.md").write_text(
            f"# 评审记录\n\n## 结论\n\n{conclusion}\n", encoding="utf-8"
        )


def run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定脚本路径，输入来自 tmp_path
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_命名基线与评审声称一致时通过_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "评审前置检查通过" in result.stdout


def test_组件文件与导出名不一致时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    (tmp_path / "apps" / "chat" / "features" / "demo" / "components" / "Baz.tsx").write_text(
        "export function Qux() {\n  return null;\n}\n", encoding="utf-8"
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "文件 Baz 导出 Qux" in result.stderr


def test_一文件多组件无基线时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    multi = tmp_path / "apps" / "chat" / "features" / "demo" / "components" / "Multi.tsx"
    multi.write_text(
        "export function MultiA() {\n  return null;\n}\n"
        "export function MultiB() {\n  return null;\n}\n",
        encoding="utf-8",
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "导出多个组件" in result.stderr


def test_一文件多组件有基线时通过_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    multi = tmp_path / "apps" / "chat" / "features" / "demo" / "components" / "Multi.tsx"
    multi.write_text(
        "export function MultiA() {\n  return null;\n}\n"
        "export function MultiB() {\n  return null;\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "frontend-structure-baseline.txt").write_text(
        "apps/chat/features/demo/components/Multi.tsx: FS-01\n", encoding="utf-8"
    )
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_基线过期时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    (tmp_path / "scripts" / "frontend-structure-baseline.txt").write_text(
        "apps/chat/features/demo/components/Foo.tsx: FS-01\n", encoding="utf-8"
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "基线已过期" in result.stderr


def test_基线承接引用未绑定AC的feature时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path)
    (tmp_path / "scripts" / "trace-baseline.txt").write_text(
        "AC-30: demo（F-02）\n", encoding="utf-8"
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "F-02 未绑定该 AC" in result.stderr


def test_CURRENT声称评审通过但缺评审记录时报错_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, with_review=False)
    result = run(tmp_path)
    assert result.returncode == 1
    assert "声称评审通过" in result.stderr


def test_评审结论不通过时CURRENT不得声称通过_基座豁免(tmp_path: Path) -> None:
    make_repo(tmp_path, conclusion="不通过")
    result = run(tmp_path)
    assert result.returncode == 1
    assert "结论为不通过" in result.stderr


def test_结论首句通过时历史轮次的不通过不阻断_基座豁免(tmp_path: Path) -> None:
    """首轮整改记录常写“首轮不通过（已关闭）”，最终结论仍按首句判定。"""
    make_repo(tmp_path, conclusion="通过。2 轮：首轮安全轴不通过（1 个阻塞，已关闭）。")
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "评审前置检查通过" in result.stdout


def test_计划语句中的评审通过不阻断_基座豁免(tmp_path: Path) -> None:
    """STATUS 的下一步常写“F-02 评审通过后按 F-03 开工”，这不是评审声称。"""
    make_repo(tmp_path)
    (tmp_path / "docs" / "STATUS.md").write_text(
        "# 当前项目状态\n\n## 进行中\n\n- F-01：评审通过（待收口）\n\n"
        "## 下一步\n\n1. F-02 评审通过后按 F-03 开工。\n\n## 已完成\n\n## 阻塞\n\n无\n",
        encoding="utf-8",
    )
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "评审前置检查通过" in result.stdout
