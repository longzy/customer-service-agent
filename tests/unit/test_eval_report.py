"""场景评测报告生成器：用合成 JUnit 验证 AC 聚合与失败退出码。

覆盖全绿、缺 AC、空测试集、非法 XML 与失败用例五种输入；
报告必须实际落盘，失败输入也必须留下报告。
"""

import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUN_PATH = ROOT / "evals" / "run.py"


def load_run() -> Any:
    spec = importlib.util.spec_from_file_location("eval_run", RUN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_junit(path: Path, cases: list[dict[str, Any]]) -> None:
    """按 pytest 的实际形状写 testsuites/testsuite/testcase。"""
    suite = ET.Element("testsuite", name="pytest", tests=str(len(cases)))
    for case in cases:
        node = ET.SubElement(
            suite,
            "testcase",
            classname=str(case.get("classname", "tests.unit.synthetic")),
            name=str(case["name"]),
            time=str(case.get("time", 0.01)),
        )
        status = case.get("status", "passed")
        if status == "failed":
            failure = ET.SubElement(node, "failure", message=str(case.get("message", "boom")))
            failure.text = "traceback"
        elif status == "skipped":
            ET.SubElement(node, "skipped", message=str(case.get("message", "skipped")))
    root = ET.Element("testsuites")
    root.append(suite)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def green_cases() -> list[dict[str, Any]]:
    return [
        {
            "classname": "tests.unit.synthetic",
            "name": f"test_场景_{number:02d}_AC_{number:02d}",
        }
        for number in range(1, 22)
    ]


def run_report(tmp_path: Path, cases: list[dict[str, Any]]) -> tuple[int, dict[str, Any], Path]:
    junit = tmp_path / "junit.xml"
    reports = tmp_path / "reports"
    write_junit(junit, cases)
    code = load_run().main(["--junit", str(junit), "--reports-dir", str(reports)])
    payload = json.loads((reports / "latest.json").read_text(encoding="utf-8"))
    return code, payload, reports


def test_全绿报告覆盖21条AC_基座豁免(tmp_path: Path) -> None:
    code, report, reports = run_report(tmp_path, green_cases())

    assert code == 0
    assert report["ok"] is True
    assert report["totals"]["tests"] == 21
    assert report["totals"]["passed"] == 21
    assert report["missing_acs"] == []
    assert [row["id"] for row in report["acs"]] == [f"AC-{i:02d}" for i in range(1, 22)]
    assert all(row["status"] == "passed" and row["tests"] == 1 for row in report["acs"])
    assert (reports / "latest.md").is_file()
    assert "21/21" in (reports / "latest.md").read_text(encoding="utf-8")
    timestamped = [
        path
        for path in reports.glob("*.json")
        if re.fullmatch(r"\d{8}T\d{6}Z(?:-\d+)?\.json", path.name)
    ]
    assert timestamped, "缺少带时间戳的历史报告"


def test_缺任一AC报告缺失并退出1_基座豁免(tmp_path: Path) -> None:
    cases = [case for case in green_cases() if "_AC_15" not in str(case["name"])]
    code, report, reports = run_report(tmp_path, cases)

    assert code == 1
    assert report["ok"] is False
    assert report["missing_acs"] == ["AC-15"]
    assert next(row for row in report["acs"] if row["id"] == "AC-15")["status"] == "missing"
    assert any("AC-15" in item for item in report["errors"])
    assert (reports / "latest.json").is_file()
    assert (reports / "latest.md").is_file()


def test_空测试集退出1并写报告_基座豁免(tmp_path: Path) -> None:
    code, report, reports = run_report(tmp_path, [])

    assert code == 1
    assert report["ok"] is False
    assert report["totals"]["tests"] == 0
    assert any("没有测试用例" in item for item in report["errors"])
    assert (reports / "latest.json").is_file()


def test_非法XML退出1并写失败报告_基座豁免(tmp_path: Path) -> None:
    junit = tmp_path / "broken.xml"
    junit.write_text("<testsuites><testsuite>", encoding="utf-8")
    reports = tmp_path / "reports"

    code = load_run().main(["--junit", str(junit), "--reports-dir", str(reports)])

    assert code == 1
    report = json.loads((reports / "latest.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert any("解析失败" in item for item in report["errors"])
    assert (reports / "latest.md").is_file()


def test_失败用例记录名称并退出1_基座豁免(tmp_path: Path) -> None:
    cases = green_cases()
    cases[3] = {**cases[3], "status": "failed", "message": "断言失败"}
    code, report, _reports = run_report(tmp_path, cases)

    assert code == 1
    assert report["totals"]["failed"] == 1
    assert report["failed_tests"][0]["name"].endswith("_AC_04")
    assert report["failed_tests"][0]["message"] == "断言失败"
    assert next(row for row in report["acs"] if row["id"] == "AC-04")["status"] == "failed"


def test_一个测试名可聚合多条AC_基座豁免(tmp_path: Path) -> None:
    cases = [
        {"name": "test_同时覆盖_AC_04_AC_05"},
        *green_cases(),
    ]
    code, report, _reports = run_report(tmp_path, cases)

    assert code == 0
    assert next(row for row in report["acs"] if row["id"] == "AC-04")["tests"] == 2
    assert next(row for row in report["acs"] if row["id"] == "AC-05")["tests"] == 2
