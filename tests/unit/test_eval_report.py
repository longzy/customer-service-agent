"""场景评测报告生成器：用合成 JUnit 验证 AC 聚合与失败退出码。

AC 集合来自当前 `docs/specs/*/requirements.md`；`scripts/trace-baseline.txt` 登记的
待开工 AC 记 pending，不算缺失。覆盖全绿、缺 AC、空测试集、非法 XML 与失败
用例；报告必须实际落盘，失败输入也必须留下报告。
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


def current_ac_ids() -> list[str]:
    return load_run().discover_ac_ids()


def baseline_acs() -> set[str]:
    return load_run().read_baseline()


def active_acs() -> list[str]:
    """当前 spec 中已有测试承接的 AC；baseline 里的待开工 AC 不属于此类。"""
    baseline = baseline_acs()
    return [ac for ac in current_ac_ids() if ac not in baseline]


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


def case_for(ac: str) -> dict[str, Any]:
    number = ac.removeprefix("AC-")
    return {"classname": "tests.unit.synthetic", "name": f"test_场景_{number}_AC_{number}"}


def green_cases() -> list[dict[str, Any]]:
    return [case_for(ac) for ac in active_acs()]


def run_report(tmp_path: Path, cases: list[dict[str, Any]]) -> tuple[int, dict[str, Any], Path]:
    junit = tmp_path / "junit.xml"
    reports = tmp_path / "reports"
    write_junit(junit, cases)
    code = load_run().main(["--junit", str(junit), "--reports-dir", str(reports)])
    payload = json.loads((reports / "latest.json").read_text(encoding="utf-8"))
    return code, payload, reports


def test_全绿报告覆盖当前AC_基座豁免(tmp_path: Path) -> None:
    code, report, reports = run_report(tmp_path, green_cases())
    active = active_acs()
    pending = sorted(set(current_ac_ids()) & baseline_acs())

    assert code == 0
    assert report["ok"] is True
    assert report["totals"]["tests"] == len(active)
    assert report["missing_acs"] == []
    assert report["pending_acs"] == pending
    assert [row["id"] for row in report["acs"]] == current_ac_ids()
    assert all(
        row["status"] == "passed" and row["tests"] == 1
        for row in report["acs"]
        if row["id"] in active
    )
    assert all(
        row["status"] == "pending" and row["tests"] == 0
        for row in report["acs"]
        if row["id"] in pending
    )
    assert (reports / "latest.md").is_file()
    assert f"{len(active)}/{len(current_ac_ids())}" in (reports / "latest.md").read_text(
        encoding="utf-8"
    )
    timestamped = [
        path
        for path in reports.glob("*.json")
        if re.fullmatch(r"\d{8}T\d{6}Z(?:-\d+)?\.json", path.name)
    ]
    assert timestamped, "缺少带时间戳的历史报告"


def test_基线内AC缺失记待开工且不失败_基座豁免(tmp_path: Path) -> None:
    code, report, _reports = run_report(tmp_path, green_cases())
    pending = sorted(set(current_ac_ids()) & baseline_acs())

    assert code == 0
    assert report["pending_acs"] == pending
    assert all(row["status"] == "pending" for row in report["acs"] if row["id"] in pending)


def test_缺任一AC报告缺失并退出1_基座豁免(tmp_path: Path) -> None:
    missing_ac = active_acs()[0]
    cases = [
        case
        for case in green_cases()
        if f"_AC_{missing_ac.removeprefix('AC-')}" not in case["name"]
    ]
    code, report, reports = run_report(tmp_path, cases)

    assert code == 1
    assert report["ok"] is False
    assert report["missing_acs"] == [missing_ac]
    assert next(row for row in report["acs"] if row["id"] == missing_ac)["status"] == "missing"
    assert any(missing_ac in item for item in report["errors"])
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
    target = active_acs()[0]
    cases = green_cases()
    cases[0] = {**cases[0], "status": "failed", "message": "断言失败"}
    code, report, _reports = run_report(tmp_path, cases)

    assert code == 1
    assert report["totals"]["failed"] == 1
    assert report["failed_tests"][0]["name"].endswith(f"_AC_{target.removeprefix('AC-')}")
    assert report["failed_tests"][0]["message"] == "断言失败"
    assert next(row for row in report["acs"] if row["id"] == target)["status"] == "failed"


def test_一个测试名可聚合多条AC_基座豁免(tmp_path: Path) -> None:
    first, second = active_acs()[:2]
    cases = [
        {"name": f"test_同时覆盖_AC_{first.removeprefix('AC-')}_AC_{second.removeprefix('AC-')}"},
        *green_cases(),
    ]
    code, report, _reports = run_report(tmp_path, cases)

    assert code == 0
    assert next(row for row in report["acs"] if row["id"] == first)["tests"] == 2
    assert next(row for row in report["acs"] if row["id"] == second)["tests"] == 2
