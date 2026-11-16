#!/usr/bin/env python3
"""场景评测报告生成器：把 pytest JUnit 的 `_AC_XX` 聚合为 AC 覆盖报告。

只读 JUnit，不重新执行测试。缺任一 AC、空测试集、XML 解析失败、任一测试失败
都按失败处理；失败也写 `latest.json`/`latest.md` 与带时间戳的历史报告。

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

AC_IDS = tuple(f"AC-{number:02d}" for number in range(1, 22))
AC_PATTERN = re.compile(r"_AC_(\d{2})")
SCENARIO_MODULE = "test_eval_scenarios"
DEFAULT_REPORTS_DIR = Path("evals/reports")
STATUS_TEXT = {"passed": "通过", "failed": "失败", "skipped": "跳过", "missing": "缺失"}


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
) -> dict[str, Any]:
    errors: list[str] = []
    if error:
        errors.append(error)
    elif not cases:
        errors.append("JUnit 中没有测试用例")

    by_ac: dict[str, list[TestCase]] = {ac: [] for ac in AC_IDS}
    for case in cases:
        for ac in _ac_tags(case.name):
            if ac in by_ac:
                by_ac[ac].append(case)

    acs: list[dict[str, Any]] = []
    missing: list[str] = []
    for ac in AC_IDS:
        tagged = by_ac[ac]
        failed_tests = [
            {"name": case.name, "classname": case.classname, "status": case.status}
            for case in tagged
            if case.status != "passed"
        ]
        if not tagged:
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

    scenarios = [
        {
            "name": case.name,
            "classname": case.classname,
            "status": case.status,
            "duration_seconds": round(case.duration_seconds, 3),
        }
        for case in cases
        if SCENARIO_MODULE in case.classname
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
            "covered": len(AC_IDS) - len(missing),
            "total": len(AC_IDS),
        },
        "acs": acs,
        "missing_acs": missing,
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
        f"- AC 覆盖：{coverage['covered']}/{coverage['total']}",
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
        lines.append("（本次 JUnit 未包含多轮场景）")

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
    conclusion = "通过" if report["ok"] else "失败"
    print(
        f"场景评测{conclusion}（退出码 {report['exit_code']}）："
        f"AC {report['ac_coverage']['covered']}/{report['ac_coverage']['total']}，"
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

    report = build_report(cases, junit=junit, generated_at=generated_at, error=error)
    try:
        reports = write_reports(report, reports_dir, generated_at)
    except OSError as exc:
        print(f"报告写入失败：{exc}", file=sys.stderr)
        return 1
    print_summary(report, reports)
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
