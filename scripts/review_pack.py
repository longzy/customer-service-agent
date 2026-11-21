#!/usr/bin/env python3
"""生成两轴评审的输入包：固定点、差异、AC 原文、执行卡决策、门禁命令。

评审包只放事实，不放结论；评审者仍独立读代码、跑定向测试并给结论。
用法：
    python3 scripts/review_pack.py F-08
    python3 scripts/review_pack.py F-08 --base 9ea5cb2 --output /tmp/F-08-review.md
未指定 --base 时按 `feat(F-XX)` 的首个提交自动推导父提交。
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = shutil.which("git") or "git"
SPECS = ROOT / "docs" / "specs"
TASKS = ROOT / "docs" / "tasks"
REVIEWS = ROOT / "docs" / "reviews"

AC_ID = re.compile(r"AC-\d{2}")

STANDARDS = (
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/process/standards.md",
    "docs/process/frontend.md",
    "docs/architecture/invariants.md",
    "docs/architecture/overview.md",
    "docs/process/WORKFLOW.md",
    "docs/process/review-checklist.md",
    "docs/process/review-prompts.md",
)


def git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 - 固定 git 与仓库内参数
        [GIT, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{result.stderr.strip()}")
    return result.stdout


def find_feature(feature: str) -> tuple[str, list[str]]:
    for path in sorted(SPECS.glob("*/features.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith(f"| {feature} |"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != 7:
                raise SystemExit(f"{path}：{feature} 行不是 7 列")
            return path.parent.name, cells
    raise SystemExit(f"{feature}：在 docs/specs/*/features.md 中找不到对应行")


def detect_base(feature: str) -> str:
    """取第一条 subject 提到 F-XX 的提交的父提交，不限定 feat/test/docs 类型。

    兼容 `feat(F-26)` 与 `feat(003): F-26 ...` 两种 scope 惯例。
    """
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(feature)}(?![0-9])")
    for line in git("log", "--reverse", "--format=%H%x09%s").splitlines():
        sha, _, subject = line.partition("\t")
        if f"({feature})" in subject or pattern.search(subject):
            return f"{sha}^"
    raise SystemExit(
        f"无法自动识别 {feature} 的固定点：找不到 subject 提到 {feature} 的提交；请用 --base 指定。"
    )


def section(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.MULTILINE)
    if match is None:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: end.start()].strip() if end else rest.strip()


def brief_ac_rows(spec: str, acs: list[str]) -> str:
    lines = (SPECS / spec / "brief.md").read_text(encoding="utf-8").splitlines()
    header: list[str] = []
    rows: list[str] = []
    for line in lines:
        if line.startswith("| AC |"):
            header = [line, "|---|---|---|---|"]
            continue
        if any(line.startswith(f"| {ac} |") for ac in acs):
            rows.append(line)
    if not rows:
        return "（brief 中未找到对应 AC 行）"
    return "\n".join([*header, *rows]) if header else "\n".join(rows)


def build(feature: str, base: str) -> str:
    spec, cells = find_feature(feature)
    acs = list(dict.fromkeys(AC_ID.findall(cells[4])))
    ac_filter = " or ".join(ac.replace("-", "_") for ac in acs) if acs else "F_08"
    card_path = TASKS / spec / f"{feature}.md"
    review_path = REVIEWS / spec / f"{feature}.md"
    card = card_path.read_text(encoding="utf-8") if card_path.exists() else ""
    plan = (SPECS / spec / "plan.md").read_text(encoding="utf-8")
    commits = git("log", "--oneline", f"{base}..HEAD").strip() or "（无提交差异）"
    diff_stat = git("diff", "--stat", f"{base}...HEAD").strip() or "（无差异）"
    changed = git("diff", "--name-only", f"{base}...HEAD").strip() or "（无）"
    slug = feature.lower().replace("-", "_")
    db_name = f"customer_service_review_{slug}_std"

    parts = [
        f"# {feature} 评审包",
        "",
        f"- 规格：`docs/specs/{spec}/`",
        f"- 执行卡：`docs/tasks/{spec}/{feature}.md`",
        f"- 评审记录：`docs/reviews/{spec}/{feature}.md`"
        + ("" if review_path.exists() else "（待创建）"),
        f"- 固定点：`{base}`",
        f"- HEAD：`{git('rev-parse', '--short', 'HEAD').strip()}`",
        f"- 绑定验收：{'、'.join(acs) or '—'}",
        "",
        "## 0. 评审方式",
        "",
        "- 两轴并行、独立上下文：Standards 轴与 Spec 轴；"
        "提示词见 `docs/process/review-prompts.md`。",
        "- 先跑 `make review-check`（机械前置）；门禁仍是 `make verify-check`（全量）。",
        "- 评审包只提供事实；结论、阻断项与逐 AC 证据由评审者给出。",
        "",
        "## 1. 提交与差异",
        "",
        "### commits",
        "",
        commits,
        "",
        "### diff stat",
        "",
        diff_stat,
        "",
        "### changed files",
        "",
        changed,
        "",
        f"完整 diff 用 `git diff {base}...HEAD`；本包不重复贴 diff，避免与代码重复。",
        "",
        f"## 2. 验收原文（{'、'.join(acs) or '—'}）",
        "",
        brief_ac_rows(spec, acs),
        "",
        "## 3. features 行",
        "",
        "| " + " | ".join(cells) + " |",
        "",
        "## 4. 执行卡：改变范围与任务决策",
        "",
        section(card, "1. 改变范围") or "（执行卡 §1 不存在）",
        "",
        section(card, "2. 任务级决策") or "（执行卡 §2 不存在）",
        "",
        "## 5. 规格 plan 全文",
        "",
        plan.strip(),
        "",
        "## 6. 评审命令",
        "",
        "```bash",
        "make review-check",
        "make verify-check",
        f'TEST_DB_NAME={db_name} ./scripts/test-db.sh tests/integration -k "{ac_filter}" -q',
        f'TEST_DB_NAME={db_name} ./scripts/test-db.sh -k "{ac_filter}" -q',
        "```",
        "",
        "## 7. Standards 来源（按需读取）",
        "",
        "\n".join(f"- `{path}`" for path in STANDARDS),
        "",
        "工具已强制的不必报（ruff/mypy/prettier/eslint、契约生成物、测试命名）。",
        "",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成两轴评审包")
    parser.add_argument("feature", help="feature 编号，如 F-08")
    parser.add_argument("--base", help="固定点（改动的父提交）；默认按 feat(F-XX) 推导")
    parser.add_argument("--output", type=Path, help="写入文件；默认打印到 stdout")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"F-\d{2}", args.feature):
        print(f"feature 编号不合法：{args.feature}", file=sys.stderr)
        return 2
    base = args.base or detect_base(args.feature)
    pack = build(args.feature, base)
    if args.output:
        args.output.write_text(pack + "\n", encoding="utf-8")
        print(f"已生成评审包：{args.output}")
    else:
        print(pack)
    return 0


if __name__ == "__main__":
    sys.exit(main())
