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


def test_ac_from_features读取Passes_基座豁免(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_module()
    spec_dir = tmp_path / "001-demo"
    spec_dir.mkdir()
    (spec_dir / "features.md").write_text(
        "| ID | Category | Description | Steps | AC | Passes | Evidence |\n"
        "|---|---|---|---|---|---|---|\n"
        "| F-06 | functional | demo | pytest | AC-35 | true | evidence |\n"
        "| F-07 | security | demo | pytest | AC-35 | false | — |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "SPECS", tmp_path)

    assert module.ac_from_features() == {
        "AC-35": [("F-06", True), ("F-07", False)],
    }
