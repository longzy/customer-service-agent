"""模板契约：按模板填写的 spec 必须满足 AC 追溯与结构门禁。"""

import importlib.util
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "docs" / "templates"


def _read(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def _fill(text: str) -> str:
    """把模板占位符替换成可解析的编号，模拟一次真实填写。"""
    return (
        text.replace("<feature>", "fixture")
        .replace("AC-XX", "AC-01")
        .replace("AC-YY", "AC-02")
        .replace("F-XX", "F-01")
        .replace("F-YY", "F-02")
    )


def _load_trace() -> Any:
    path = ROOT / "scripts" / "trace.py"
    spec = importlib.util.spec_from_file_location("spec_trace", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _feature_rows(text: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.startswith("| F-")
    ]


def test_brief_template_has_pr_faq_and_ac_gate() -> None:
    brief = _read("brief.md")
    assert re.search(r"^- 状态：", brief, re.M)
    assert "客户新闻稿（Press Release）" in brief
    assert "外部 FAQ" in brief
    assert "内部 FAQ" in brief
    assert re.search(r"^\| AC-XX \|", brief, re.M)


def test_plan_template_follows_google_design_doc_sections() -> None:
    plan = _read("plan.md")
    for heading in (
        "Context and Scope",
        "Goals and Non-Goals",
        "The Design",
        "Alternatives Considered",
        "Cross-cutting Concerns",
    ):
        assert heading in plan


def test_features_template_follows_anthropic_feature_list_fields() -> None:
    features = _read("features.md")
    header = next(line for line in features.splitlines() if line.startswith("| ID |"))
    for column in ("Category", "Description", "Steps", "AC", "Passes", "Evidence"):
        assert column in header
    rows = _feature_rows(features)
    assert len(rows) >= 2
    for row in rows:
        assert len(row) == 7
        assert row[5] == "false"
        assert row[6] == "—"


def test_filled_templates_satisfy_ac_traceability(tmp_path: Path) -> None:
    brief = _fill(_read("brief.md"))
    features = _fill(_read("features.md"))
    brief_path = tmp_path / "brief.md"
    brief_path.write_text(brief, encoding="utf-8")
    acs = _load_trace().ac_from_requirements(brief_path)
    assert acs == ["AC-01", "AC-02"]
    for ac in acs:
        assert ac in features
