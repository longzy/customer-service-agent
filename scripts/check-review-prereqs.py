#!/usr/bin/env python3
"""评审前置机械检查：组件命名、trace 基线归属、CURRENT 评审声称一致。

这些规则都能从仓库事实判定，不应占用两轴评审的注意力；判断性问题仍留给评审。
检查项：
1. 组件文件与导出组件同名、一个文件只导出一个组件、feature 组件不默认导出（FE-DIR-06/07）。
2. hook 文件以 `use` 开头且导出同名 hook（FE-DIR-06）。
3. `scripts/trace-baseline.txt` 的承接理由里出现的 F-xx 必须真的绑定该 AC。
4. `docs/CURRENT.md` 声称某个 F-xx“评审通过”时，必须有对应评审记录且结论通过（STD-DOC-01）。

用法：
    python3 scripts/check-review-prereqs.py
    python3 scripts/check-review-prereqs.py --root PATH   # 测试用
退出码：0 通过；1 有违规。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from review_conclusion import conclusion_verdict

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "docs" / "specs"
REVIEWS = ROOT / "docs" / "reviews"
CURRENT = ROOT / "docs" / "CURRENT.md"
STRUCTURE_BASELINE = ROOT / "scripts" / "frontend-structure-baseline.txt"
TRACE_BASELINE = ROOT / "scripts" / "trace-baseline.txt"

FEATURE_ID = re.compile(r"\bF-\d{2}\b")
TRACE_LINE = re.compile(r"^(AC-\d{2}):\s*(.*)$")

EXPORT_FUNCTION = re.compile(r"^export function ([A-Z]\w*)\s*[(<]", re.MULTILINE)
EXPORT_CONST = re.compile(
    r"^export const ([A-Z]\w*)\s*(?::[^=\n]+)?=\s*(?:async\s*)?(?:\(|function\b)",
    re.MULTILINE,
)
EXPORT_HOOK = re.compile(r"^export (?:function|const) (use[A-Z]\w*)", re.MULTILINE)
DEFAULT_EXPORT = re.compile(r"^export default\b", re.MULTILINE)

RULE_MULTI_COMPONENT = "FS-01"
RULE_NAME_MISMATCH = "FS-02"
RULE_DEFAULT_EXPORT = "FS-03"
RULE_NO_COMPONENT = "FS-04"
RULE_HOOK = "FS-05"


@dataclass(frozen=True)
class Violation:
    path: str
    rule: str
    detail: str

    def key(self) -> tuple[str, str]:
        return (self.path, self.rule)


def configure(root: Path) -> None:
    """允许测试用临时仓库根目录运行，不依赖调用点位置。"""
    global ROOT, SPECS, REVIEWS, CURRENT, STRUCTURE_BASELINE, TRACE_BASELINE
    ROOT = root.resolve()
    SPECS = ROOT / "docs" / "specs"
    REVIEWS = ROOT / "docs" / "reviews"
    CURRENT = ROOT / "docs" / "CURRENT.md"
    STRUCTURE_BASELINE = ROOT / "scripts" / "frontend-structure-baseline.txt"
    TRACE_BASELINE = ROOT / "scripts" / "trace-baseline.txt"


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _component_files() -> list[Path]:
    return sorted(
        {
            *ROOT.glob("apps/*/features/*/components/*.tsx"),
            *ROOT.glob("apps/*/components/*.tsx"),
            *ROOT.glob("apps/*/components/**/*.tsx"),
        }
    )


def _hook_files() -> list[Path]:
    return sorted(ROOT.glob("apps/*/features/*/hooks/*.ts"))


def _component_names(text: str) -> list[str]:
    names = [
        *EXPORT_FUNCTION.findall(text),
        *EXPORT_CONST.findall(text),
    ]
    return sorted(set(names))


def component_violations() -> list[Violation]:
    violations: list[Violation] = []
    for path in _component_files():
        relative = _relative(path)
        text = path.read_text(encoding="utf-8")
        names = _component_names(text)
        if not names:
            violations.append(Violation(relative, RULE_NO_COMPONENT, "未导出组件"))
        elif len(names) > 1:
            violations.append(
                Violation(relative, RULE_MULTI_COMPONENT, f"导出多个组件：{', '.join(names)}")
            )
        elif names[0] != path.stem:
            violations.append(
                Violation(relative, RULE_NAME_MISMATCH, f"文件 {path.stem} 导出 {names[0]}")
            )
        if DEFAULT_EXPORT.search(text):
            violations.append(Violation(relative, RULE_DEFAULT_EXPORT, "feature 组件不得默认导出"))
    return violations


def hook_violations() -> list[Violation]:
    violations: list[Violation] = []
    for path in _hook_files():
        relative = _relative(path)
        text = path.read_text(encoding="utf-8")
        exported = set(EXPORT_HOOK.findall(text))
        if not path.stem.startswith("use"):
            violations.append(Violation(relative, RULE_HOOK, "hook 文件名必须以 use 开头"))
        elif path.stem not in exported:
            violations.append(Violation(relative, RULE_HOOK, f"未导出同名 hook {path.stem}"))
    return violations


def read_structure_baseline() -> set[tuple[str, str]]:
    if not STRUCTURE_BASELINE.exists():
        return set()
    entries: set[tuple[str, str]] = set()
    for line in STRUCTURE_BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        path, _, rule = line.rpartition(":")
        if not path or not rule.strip():
            continue
        entries.add((path.strip(), rule.strip()))
    return entries


def structure_violations() -> list[str]:
    """返回新增违规与过期基线；存量基线只减不增。"""
    violations = component_violations() + hook_violations()
    baseline = read_structure_baseline()
    errors: list[str] = []
    current = {violation.key() for violation in violations}
    for violation in violations:
        if violation.key() not in baseline:
            errors.append(f"{violation.path}：{violation.rule} {violation.detail}（FE-DIR-06/07）")
    for path, rule in sorted(baseline - current):
        errors.append(f"{path}：{rule} 基线已过期，违规已修复，请删除对应基线行")
    return errors


def feature_acs() -> dict[str, tuple[str, set[str]]]:
    mapping: dict[str, tuple[str, set[str]]] = {}
    for path in sorted(SPECS.glob("*/features.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("| F-"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 6:
                continue
            mapping[cells[0]] = (
                path.parent.name,
                set(re.findall(r"AC-\d{2}", cells[4])),
            )
    return mapping


def trace_baseline_violations() -> list[str]:
    if not TRACE_BASELINE.exists():
        return []
    features = feature_acs()
    errors: list[str] = []
    for line in TRACE_BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = TRACE_LINE.match(line)
        if match is None:
            continue
        ac, reason = match.group(1), match.group(2)
        for feature in sorted(set(FEATURE_ID.findall(reason))):
            if feature not in features:
                errors.append(f"{TRACE_BASELINE.name}：{ac} 的承接引用了不存在的 {feature}")
            elif ac not in features[feature][1]:
                bound = ", ".join(sorted(features[feature][1])) or "无"
                errors.append(
                    f"{TRACE_BASELINE.name}：{ac} 的承接写了 {feature}，"
                    f"但 {feature} 未绑定该 AC（实际绑定 {bound}）"
                )
    return errors


def current_review_violations() -> list[str]:
    if not CURRENT.exists():
        return []
    features = feature_acs()
    errors: list[str] = []
    for lineno, line in enumerate(CURRENT.read_text(encoding="utf-8").splitlines(), 1):
        if "评审通过" not in line:
            continue
        for feature in sorted(set(FEATURE_ID.findall(line))):
            found = features.get(feature)
            if found is None:
                errors.append(f"docs/CURRENT.md:{lineno}：{feature} 未在 features 中定义")
                continue
            review = REVIEWS / found[0] / f"{feature}.md"
            if not review.exists():
                errors.append(
                    f"docs/CURRENT.md:{lineno}：{feature} 声称评审通过，"
                    f"但 {_relative(review)} 不存在"
                )
                continue
            verdict = conclusion_verdict(review.read_text(encoding="utf-8"))
            if verdict == "不通过":
                errors.append(f"{review.relative_to(ROOT)}：结论为不通过，CURRENT 不得声称通过")
            elif verdict is None:
                errors.append(f"{review.relative_to(ROOT)}：结论未写明通过")
    return errors


def check() -> list[str]:
    return [
        *structure_violations(),
        *trace_baseline_violations(),
        *current_review_violations(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="评审前置机械检查")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    configure(args.root)

    errors = check()
    if errors:
        print(f"评审前置检查失败，{len(errors)} 个问题：", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    components = len(_component_files())
    hooks = len(_hook_files())
    print(
        f"评审前置检查通过：{components} 个组件、{hooks} 个 hook、"
        "trace 基线与 CURRENT 评审声称一致。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
