"""门禁反馈指标：评审结论、T3 安全覆盖与评测摘要。"""

import json
from pathlib import Path

from scripts import gate_metrics


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_汇总评审与T3安全覆盖_基座豁免(tmp_path: Path) -> None:
    write(
        tmp_path / "docs/tasks/001-demo/F-01.md",
        "---\nid: F-01\nrisk: T3\nstatus: done\n---\n",
    )
    write(
        tmp_path / "docs/reviews/001-demo/F-01.md",
        "## 安全评审（T3）\n\n结论：通过\n\n## 结论\n\n通过\n",
    )
    write(
        tmp_path / "docs/reviews/001-demo/F-02.md",
        "## 结论\n\n有条件通过。\n\n接受为后续：2\n",
    )
    result = gate_metrics.collect(tmp_path)
    reviews = result["reviews"]
    assert reviews["reviews"] == 2
    assert reviews["verdicts"] == {"通过": 1, "有条件通过": 1}
    assert reviews["t3_cards"] == 1
    assert reviews["t3_security_passed"] == 1
    assert reviews["followups"] == 1


def test_最近评测摘要_基座豁免(tmp_path: Path) -> None:
    write(
        tmp_path / "evals/reports/latest.json",
        json.dumps(
            {
                "ok": True,
                "totals": {"tests": 10, "passed": 9, "failed": 1, "skipped": 0},
                "ac_coverage": {"covered": 3, "total": 4, "pending": 1},
            }
        ),
    )
    data = gate_metrics.collect(tmp_path)
    assert data["latest_eval"] == {
        "ok": True,
        "tests": 10,
        "passed": 9,
        "failed": 1,
        "skipped": 0,
        "ac_covered": 3,
        "ac_total": 4,
        "ac_pending": 1,
    }
    assert "AC 3/4" in gate_metrics.render(data)


def test_无评测报告时说明_基座豁免(tmp_path: Path) -> None:
    data = gate_metrics.collect(tmp_path)
    assert data["latest_eval"] is None
    assert "无报告" in gate_metrics.render(data)
