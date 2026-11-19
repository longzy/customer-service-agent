#!/usr/bin/env python3
"""场景评测报告生成器：把 pytest JUnit 的 `_AC_XX` 聚合为 AC 覆盖报告。

AC 集合从当前 `docs/specs/*/brief.md` 动态发现；`AC-01~29` 是 M1-P 历史标签，
不参与门禁；`scripts/trace-baseline.txt` 中登记的待开工 AC 记 `pending`，
不算缺失。只读 JUnit，不重新执行测试。缺未登记的 AC、空测试集、XML 解析失败、
任一测试失败都按失败处理；失败也写 `latest.json`/`latest.md` 与带时间戳的历史报告。

用法：
    python3 evals/run.py
    python3 evals/run.py --junit evals/reports/latest-junit.xml --reports-dir evals/reports
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = ROOT / "docs" / "specs"
BASELINE_PATH = ROOT / "scripts" / "trace-baseline.txt"
# M1-P 原型的验收编号只保留为历史测试标签，不再进入当前门禁。
LEGACY_AC = {f"AC-{number:02d}" for number in range(1, 30)}
AC_ROW = re.compile(r"^\| (AC-\d{2}) \|", re.MULTILINE)
AC_PATTERN = re.compile(r"_AC_(\d{2})")
SCENARIO_MODULE = "test_eval_scenarios"
DEFAULT_REPORTS_DIR = Path("evals/reports")
STATUS_TEXT = {
    "passed": "通过",
    "failed": "失败",
    "skipped": "跳过",
    "missing": "缺失",
    "pending": "待开工",
}


def discover_ac_ids(specs_dir: Path = SPECS_DIR) -> list[str]:
    """当前 spec 的 AC 集合；与 `scripts/trace.py` 同源（brief.md 的 AC 表）。"""
    found: set[str] = set()
    for path in sorted(specs_dir.glob("*/brief.md")):
        found.update(AC_ROW.findall(path.read_text(encoding="utf-8")))
    return sorted(ac for ac in found if ac not in LEGACY_AC)


def read_baseline(path: Path = BASELINE_PATH) -> set[str]:
    """`trace-baseline.txt` 中登记的待承接 AC；与 trace 门禁共用一份基线。"""
    if not path.exists():
        return set()
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        ac = entry.split(":", 1)[0].strip()
        if re.fullmatch(r"AC-\d{2}", ac):
            entries.add(ac)
    return entries


@dataclass
class TestCase:
    classname: str
    name: str
    status: str
    duration_seconds: float
    message: str = ""


def _duration(node: ET.Element) -> float:
    try:
        return float(node.get("time") or 0.0)
    except ValueError:
        return 0.0


def parse_junit(path: Path) -> list[TestCase]:
    """读取 JUnit；failure/error/skipped 都视为未通过。"""
    # 输入是 pytest 自己写在本机报告目录的 JUnit，不经过网络；ElementTree 默认不解析外部实体
    root = ET.parse(path).getroot()  # noqa: S314
    cases: list[TestCase] = []
    for node in root.iter("testcase"):
        failure = node.find("failure")
        if failure is None:
            failure = node.find("error")
        skipped = node.find("skipped")
        if failure is not None:
            status = "failed"
            message = (failure.get("message") or "").strip()
        elif skipped is not None:
            status = "skipped"
            message = (skipped.get("message") or "").strip()
        else:
            status = "passed"
            message = ""
        cases.append(
            TestCase(
                classname=node.get("classname") or "",
                name=node.get("name") or "",
                status=status,
                duration_seconds=_duration(node),
                message=message,
            )
        )
    return cases


def _ac_tags(name: str) -> list[str]:
    return [f"AC-{number}" for number in dict.fromkeys(AC_PATTERN.findall(name))]


def build_report(
    cases: list[TestCase],
    *,
    junit: Path,
    generated_at: datetime,
    error: str | None,
    ac_ids: list[str],
    baseline: set[str],
) -> dict[str, Any]:
    errors: list[str] = []
    if error:
        errors.append(error)
    elif not cases:
        errors.append("JUnit 中没有测试用例")
    elif not ac_ids:
        errors.append("当前 spec 没有可判定的 AC")

    by_ac: dict[str, list[TestCase]] = {ac: [] for ac in ac_ids}
    for case in cases:
        for ac in _ac_tags(case.name):
            if ac in by_ac:
                by_ac[ac].append(case)

    acs: list[dict[str, Any]] = []
    missing: list[str] = []
    pending: list[str] = []
    for ac in ac_ids:
        tagged = by_ac[ac]
        failed_tests = [
            {"name": case.name, "classname": case.classname, "status": case.status}
            for case in tagged
            if case.status != "passed"
        ]
        if not tagged:
            if ac in baseline:
                status = "pending"
                pending.append(ac)
            else:
                status = "missing"
                missing.append(ac)
        elif failed_tests:
            status = "failed"
        else:
            status = "passed"
        acs.append(
            {
                "id": ac,
                "status": status,
                "tests": len(tagged),
                "passed": sum(case.status == "passed" for case in tagged),
                "failed": len(failed_tests),
                "failed_tests": failed_tests,
            }
        )

    if missing and not error and cases:
        errors.append(f"缺少验收用例：{', '.join(missing)}")

    failed_tests = [
        {
            "name": case.name,
            "classname": case.classname,
            "status": case.status,
            "message": case.message,
        }
        for case in cases
        if case.status != "passed"
    ]
    for case in failed_tests:
        code = f"{case['classname']}::{case['name']}"
        if case["status"] == "skipped":
            errors.append(f"测试被跳过（不算通过）：{code}")
        else:
            errors.append(f"测试失败：{code}")

    # 只列覆盖当前 AC 的场景；M1-P 场景（AC-01~08）不进入当前报告。
    scenarios = [
        {
            "name": case.name,
            "classname": case.classname,
            "status": case.status,
            "duration_seconds": round(case.duration_seconds, 3),
        }
        for case in cases
        if SCENARIO_MODULE in case.classname and any(ac in by_ac for ac in _ac_tags(case.name))
    ]

    passed = sum(case.status == "passed" for case in cases)
    skipped = sum(case.status == "skipped" for case in cases)
    return {
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "junit": str(junit),
        "ok": not errors,
        "exit_code": 0 if not errors else 1,
        "totals": {
            "tests": len(cases),
            "passed": passed,
            "failed": len(cases) - passed - skipped,
            "skipped": skipped,
            "duration_seconds": round(sum(case.duration_seconds for case in cases), 3),
        },
        "ac_coverage": {
            "covered": len(ac_ids) - len(missing) - len(pending),
            "total": len(ac_ids),
            "pending": len(pending),
        },
        "acs": acs,
        "missing_acs": missing,
        "pending_acs": pending,
        "failed_tests": failed_tests,
        "scenarios": scenarios,
        "errors": errors,
    }


def _timestamp_path(reports_dir: Path, generated_at: datetime) -> Path:
    stem = generated_at.strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"{stem}.json"
    suffix = 1
    while path.exists():
        path = reports_dir / f"{stem}-{suffix}.json"
        suffix += 1
    return path


def render_markdown(report: dict[str, Any]) -> str:
    totals = report["totals"]
    coverage = report["ac_coverage"]
    conclusion = "通过" if report["ok"] else "失败"
    scenario_passed = sum(1 for item in report["scenarios"] if item["status"] == "passed")
    lines = [
        "# 场景评测报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- JUnit 输入：`{report['junit']}`",
        f"- 结论：**{conclusion}**（退出码 {report['exit_code']}）",
        (
            f"- 用例：{totals['tests']} 个，{totals['passed']} 通过，"
            f"{totals['failed']} 失败，{totals['skipped']} 跳过"
        ),
        f"- AC 覆盖：{coverage['covered']}/{coverage['total']}"
        + (f"（待开工 {coverage['pending']}）" if coverage["pending"] else ""),
        f"- 多轮场景：{scenario_passed}/{len(report['scenarios'])} 通过",
        "",
        "## AC 覆盖",
        "",
        "| AC | 状态 | 测试数 | 通过 | 失败/跳过 |",
        "|---|---|---|---|---|",
    ]
    for row in report["acs"]:
        lines.append(
            f"| {row['id']} | {STATUS_TEXT[row['status']]} | {row['tests']} | "
            f"{row['passed']} | {row['failed']} |"
        )

    lines.extend(["", "## 多轮场景", ""])
    if report["scenarios"]:
        lines.extend(["| 场景 | 状态 | 耗时(s) |", "|---|---|---|"])
        for item in report["scenarios"]:
            lines.append(
                f"| `{item['name']}` | {STATUS_TEXT[item['status']]} | "
                f"{item['duration_seconds']:.3f} |"
            )
    else:
        lines.append("（当前 AC 未登记多轮场景；M1-P 场景测试仍由 pytest 覆盖）")

    lines.extend(["", "## 失败测试", ""])
    if report["failed_tests"]:
        for item in report["failed_tests"]:
            message = " ".join(item["message"].split())[:200]
            suffix = f"：{message}" if message else ""
            lines.append(
                f"- `{item['classname']}::{item['name']}`（{STATUS_TEXT[item['status']]}）{suffix}"
            )
    else:
        lines.append("无")

    lines.extend(["", "## 错误", ""])
    if report["errors"]:
        lines.extend(f"- {item}" for item in report["errors"])
    else:
        lines.append("无")
    return "\n".join(lines) + "\n"


def write_reports(
    report: dict[str, Any], reports_dir: Path, generated_at: datetime
) -> tuple[Path, Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    latest_json = reports_dir / "latest.json"
    latest_md = reports_dir / "latest.md"
    timestamped = _timestamp_path(reports_dir, generated_at)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_json.write_text(payload, encoding="utf-8")
    timestamped.write_text(payload, encoding="utf-8")
    latest_md.write_text(render_markdown(report), encoding="utf-8")
    return latest_json, timestamped, latest_md


def print_summary(report: dict[str, Any], reports: tuple[Path, Path, Path]) -> None:
    totals = report["totals"]
    coverage = report["ac_coverage"]
    conclusion = "通过" if report["ok"] else "失败"
    pending = f"（待开工 {coverage['pending']}）" if coverage["pending"] else ""
    print(
        f"场景评测{conclusion}（退出码 {report['exit_code']}）："
        f"AC {coverage['covered']}/{coverage['total']}{pending}，"
        f"用例 {totals['tests']} 个（{totals['passed']} 通过，"
        f"{totals['failed']} 失败，{totals['skipped']} 跳过）"
    )
    print(f"报告：{reports[0]}、{reports[2]}；历史：{reports[1]}")
    for item in report["errors"][:20]:
        print(f"  - {item}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把 pytest JUnit 聚合为 AC 场景评测报告")
    parser.add_argument("--junit", type=Path, help="pytest JUnit XML 路径")
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="报告输出目录（默认 evals/reports）",
    )
    args = parser.parse_args(argv)

    reports_dir: Path = args.reports_dir
    junit: Path = args.junit or reports_dir / "latest-junit.xml"
    generated_at = datetime.now(UTC)

    cases: list[TestCase] = []
    error: str | None = None
    if not junit.exists():
        error = f"JUnit 文件不存在：{junit}"
    else:
        try:
            cases = parse_junit(junit)
        except (ET.ParseError, OSError) as exc:
            error = f"JUnit 解析失败：{junit}：{exc}"

    report = build_report(
        cases,
        junit=junit,
        generated_at=generated_at,
        error=error,
        ac_ids=discover_ac_ids(),
        baseline=read_baseline(),
    )
    try:
        reports = write_reports(report, reports_dir, generated_at)
    except OSError as exc:
        print(f"报告写入失败：{exc}", file=sys.stderr)
        return 1
    print_summary(report, reports)
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
