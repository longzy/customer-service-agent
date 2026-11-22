"""全量验证复用：代码指纹只覆盖影响验证结果的输入。"""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify_state


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)  # noqa: S603, S607
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "service.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "docs" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "specs" / "requirements.md").write_text("需求\n", encoding="utf-8")
    (tmp_path / "docs" / "design-system").mkdir(parents=True)
    (tmp_path / "docs" / "design-system" / "tokens.css").write_text("--a: 1;\n", encoding="utf-8")
    return tmp_path


def test_源代码变化会改变指纹_基座豁免(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    before = verify_state.fingerprint(root)
    (root / "backend" / "service.py").write_text("x = 2\n", encoding="utf-8")
    assert verify_state.fingerprint(root) != before


def test_任务文档变化不改变指纹_基座豁免(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    before = verify_state.fingerprint(root)
    (root / "docs" / "specs" / "requirements.md").write_text("需求更新\n", encoding="utf-8")
    assert verify_state.fingerprint(root) == before


def test_设计令牌变化会改变指纹_基座豁免(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    before = verify_state.fingerprint(root)
    (root / "docs" / "design-system" / "tokens.css").write_text("--a: 2;\n", encoding="utf-8")
    assert verify_state.fingerprint(root) != before


def test_保存后同指纹可复用_基座豁免(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    state = root / ".verify" / "last-full.json"
    verify_state.save(pytest_line="894 passed in 1s", eval_status=0, path=state, root=root)
    assert verify_state.matches(state, root) is True
    assert verify_state.load(state)["pytest_line"] == "894 passed in 1s"

    (root / "backend" / "service.py").write_text("x = 3\n", encoding="utf-8")
    assert verify_state.matches(state, root) is False


def test_缺少状态文件不匹配_基座豁免(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert verify_state.matches(root / ".verify" / "missing.json", root) is False


def test_命令行检查与读取字段_基座豁免(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    state = root / ".verify" / "last-full.json"
    verify_state.save(pytest_line="1 passed", eval_status=0, path=state, root=root)

    checked = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts" / "verify_state.py"),
            "check",
            "--root",
            str(root),
            "--state",
            str(state),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize("field", ["pytest_line", "eval_status"])
def test_状态字段可读取_基座豁免(tmp_path: Path, field: str) -> None:
    root = _repo(tmp_path)
    state = root / ".verify" / "last-full.json"
    verify_state.save(pytest_line="2 passed", eval_status=0, path=state, root=root)
    assert verify_state.load(state)[field] is not None
