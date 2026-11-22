#!/usr/bin/env python3
"""Spec/Plan 门禁：批准状态、风险级别、AC、设计必填章节与执行卡 DoR。

只对“新模型”生效：docs/tasks 下带 `risk:` 的执行卡所属 spec。旧卡（无 risk）
是历史实例，不批量重写；新 spec 必须按 2026-11-21 模板写全。

用法：python3 scripts/check-spec.py [--root PATH]
退出码：0 通过；1 有违规。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AC_ROW = re.compile(r"^\|\s*(AC-\d{2})\s*\|", re.MULTILINE)
STATUS_LINE = re.compile(r"^- 状态：(.+)$", re.MULTILINE)
RISK_LINE = re.compile(r"^- 风险级别：(T[0-3])", re.MULTILINE)
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
REQUIRED_DESIGN = ("背景与范围", "目标与非目标", "方案", "备选方案", "跨切面", "未决问题")
T3_DESIGN = ("威胁", "越权矩阵", "回滚")

errors: list[str] = []


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta


def section(text: str, title: str) -> str:
    match = re.search(rf"^#{{2,3}} {re.escape(title)}[^\n]*$", text, re.MULTILINE)
    if match is None:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def check_doc_status(path: Path, label: str) -> None:
    text = read(path)
    status = STATUS_LINE.search(text)
    if status is None or not status.group(1).startswith("已批准"):
        errors.append(f"{path}：{label} 状态必须为「已批准」")
    risk = RISK_LINE.search(text) or re.search(r"^- 规模：\s*(T[0-3])", text, re.MULTILINE)
    if risk is None:
        errors.append(f"{path}：缺少「风险级别：T0–T3」或「规模：T2/T3」")


def check_requirements(path: Path) -> None:
    text = read(path)
    check_doc_status(path, "requirements")
    if not AC_ROW.findall(text):
        errors.append(f"{path}：AC 表为空")
    if "非目标" not in text:
        errors.append(f"{path}：缺少非目标")


def check_design(path: Path, *, t3: bool) -> None:
    text = read(path)
    check_doc_status(path, "design")
    missing = [item for item in REQUIRED_DESIGN if item not in text]
    if missing:
        errors.append(f"{path}：缺少设计章节 {missing}")
    if t3:
        missing_security = [item for item in T3_DESIGN if item not in text]
        if missing_security:
            errors.append(f"{path}：T3 设计缺少 {missing_security}")


def check_card(path: Path) -> None:
    text = read(path)
    meta = frontmatter(text)
    risk = meta.get("risk")
    status = meta.get("status", "")
    if risk is None:
        return  # 旧模型历史卡，不强制新模板
    if risk not in {"T0", "T1", "T2", "T3"}:
        errors.append(f"{path}：risk 非法 {risk!r}")
    if status not in {"doing", "review"}:
        return

    dor = section(text, "2.1 前置条件（Definition of Ready）")
    unchecked = [line for line in dor.splitlines() if line.strip().startswith("- [ ]")]
    checked = [line for line in dor.splitlines() if line.strip().startswith("- [x]")]
    if not dor or unchecked or len(checked) < 4:
        errors.append(f"{path}：DoR 未全部满足（未勾选 {len(unchecked)} 项）")
    if "### 1.1 触点" not in text:
        errors.append(f"{path}：缺少 §1.1 触点清单")
    if "### 2.5 判定表与失败矩阵" not in text:
        errors.append(f"{path}：缺少 §2.5 判定表")
    if risk in {"T2", "T3"}:
        release = section(text, "7. 发布与回滚（T2/T3 必填，T1 可省）")
        if not release.strip():
            errors.append(f"{path}：T2/T3 缺少 §7 发布与回滚")
    evidence = section(text, "4. 证据")
    if "git show --shortstat" not in evidence:
        errors.append(
            f"{path}：§4 证据缺少 `git show --shortstat --oneline <sha>`（数字需可机械核对）"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spec/Plan 门禁")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root
    specs = sorted((root / "docs" / "specs").glob("*/requirements.md"))
    cards = sorted((root / "docs" / "tasks").glob("*/*.md"))

    risk_by_spec: dict[str, set[str]] = {}
    for card in cards:
        meta = frontmatter(read(card))
        if meta.get("risk"):
            risk_by_spec.setdefault(card.parent.name, set()).add(meta["risk"])

    for requirements in specs:
        spec = requirements.parent.name
        check_requirements(requirements)
        design = requirements.parent / "design.md"
        if not design.exists():
            errors.append(f"{design}：缺少 design.md")
            continue
        risks = risk_by_spec.get(spec, set())
        if risks:
            check_design(design, t3="T3" in risks)
    for card in cards:
        check_card(card)

    if errors:
        print("Spec/计划门禁未通过：", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Spec/计划门禁通过：{len(specs)} 个 spec、{len(cards)} 张执行卡。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
