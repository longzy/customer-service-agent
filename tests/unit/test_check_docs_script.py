"""评审记录格式检查器的自测（基座豁免）。"""

import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_module() -> Any:
    path = ROOT / "scripts" / "check-docs.py"
    spec = importlib.util.spec_from_file_location("check_docs", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_缺少评审小节时报告_基座豁免() -> None:
    module = load_module()
    missing = module.missing_review_sections("## 结论\n\n通过\n")
    assert missing == ["## 0. 门禁复核", "## 逐 AC", "## 阻断项"]


def test_完整评审通过_基座豁免() -> None:
    module = load_module()
    content = "## 0. 门禁复核\n\n## 逐 AC\n\n## 阻断项\n\n## 结论\n\n通过\n"
    assert module.missing_review_sections(content) == []
