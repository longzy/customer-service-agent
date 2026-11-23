"""追溯检查器的自测：按 feature 区分完全覆盖与部分覆盖（基座豁免）。"""

import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_module() -> Any:
    path = ROOT / "scripts" / "trace.py"
    spec = importlib.util.spec_from_file_location("trace_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_coverage_state区分缺口部分覆盖与完全覆盖_基座豁免() -> None:
    module = load_module()

    assert module.coverage_state("AC-35", {}, {}) == ("missing", [])
    assert module.coverage_state(
        "AC-35",
        {"AC-35": ["tests/integration/test_queue_AC_35.py"]},
        {"AC-35": [("F-06", True), ("F-07", False)]},
    ) == ("partial", ["F-07"])
    assert module.coverage_state(
        "AC-35",
        {"AC-35": ["tests/integration/test_queue_AC_35.py"]},
        {"AC-35": [("F-06", True), ("F-07", True)]},
    ) == ("covered", [])


def test_ac_from_features读取frontmatter_基座豁免(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_module()
    card_dir = tmp_path / "001-demo"
    card_dir.mkdir()
    for fid, status in (("F-06", "done"), ("F-07", "doing")):
        (card_dir / f"{fid}.md").write_text(
            f"---\nid: {fid}\ntitle: demo\nspec: 001-demo\nstatus: {status}\nac: [AC-35]\n---\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(module, "CARDS", tmp_path)

    assert module.ac_from_features() == {
        "AC-35": [("F-06", True), ("F-07", False)],
    }


def test_ac_from_tests读取前端文件头_基座豁免(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_module()
    chat = tmp_path / "apps" / "chat" / "tests"
    chat.mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (chat / "Demo.test.tsx").write_text(
        '// AC-59\nimport { describe, expect, it } from "vitest";\n\n'
        'describe("demo", () => {\n  it("renders", () => {});\n});\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert module.ac_from_tests().get("AC-59") == ["apps/chat/tests/Demo.test.tsx"]


def test_草案requirements判定_基座豁免(tmp_path: Path) -> None:
    """草案 spec 的 AC 不进入追溯矩阵；状态行缺失或读不到按非草案。"""
    module = load_module()
    requirements = tmp_path / "requirements.md"
    requirements.write_text("- 状态：草案\n", encoding="utf-8")
    assert module.is_draft(requirements) is True

    requirements.write_text("- 状态：已批准\n", encoding="utf-8")
    assert module.is_draft(requirements) is False
    assert module.is_draft(tmp_path / "missing.md") is False
