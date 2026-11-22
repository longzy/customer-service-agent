#!/usr/bin/env python3
"""feature 收口检查与机械更新。

状态源只有一处：`docs/tasks/<spec>/F-XX.md` 的 frontmatter。
本脚本做两件确定性的事：
1. 检查收口前置条件（评审通过、证据完整、STATUS.md 状态一致）；
2. `--apply` 时把 frontmatter 的 `status` 改为 `done`，并重新生成 `tasks.md`。

CURRENT/STATUS 的人工摘要仍由人写：脚本只检查并打印剩余步骤，不猜摘要。
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from review_conclusion import conclusion_verdict

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
SECURITY_HEADING = "安全评审"
SECURITY_CONCLUSION = re.compile(r"结论[:：]\s*(通过|有条件通过|不通过)")
REVIEW_VERIFY_ROW = re.compile(r"^\|\s*收口全量（回填）\s*\|(.*)\|\s*$", re.M)
DIFF_CMD = re.compile(r"git show --shortstat --oneline ([0-9a-f]{7,40})")
DIFF_STAT = re.compile(
    r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?"
)

STATUS_LABEL = {
    "todo": "未开始",
    "doing": "进行中",
    "review": "待评审",
    "done": "已完成",
    "blocked": "阻塞",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, str]:
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
    match = re.search(rf"^## {re.escape(title)}\s*$", text, re.M)
    if not match:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def find_card(root: Path, feature: str) -> Path | None:
    for path in sorted((root / "docs" / "tasks").glob("*/F-*.md")):
        if path.stem == feature:
            return path
    return None


def already_closed(root: Path, feature: str) -> bool:
    card = find_card(root, feature)
    return card is not None and parse_frontmatter(read(card)).get("status") == "done"


def current_sections(path: Path) -> dict[str, str]:
    text = read(path)
    return {name: section(text, name) for name in ("已完成", "进行中", "阻塞", "下一步")}


def trace_gate(root: Path) -> str | None:
    """收口前先跑追溯矩阵：过期基线不应该等到 make verify 才暴露。"""
    script = root / "scripts" / "trace.py"
    if not script.exists():
        return None
    result = subprocess.run(  # noqa: S603 - 固定仓库内脚本与解释器
        [sys.executable, str(script), "--strict"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return None
    output = (result.stdout + result.stderr).strip().splitlines()
    return "trace.py --strict 未通过：" + " / ".join(output[-3:])


def _git_shortstat(root: Path, sha: str) -> tuple[int, int, int] | None:
    """返回提交的实际 shortstat；提交不存在或不是 git 仓库时返回 None。"""
    git = shutil.which("git")
    if git is None:
        return None
    result = subprocess.run(  # noqa: S603 - 绝对路径来自 shutil.which
        [git, "-C", str(root), "show", "--shortstat", "--format=", sha],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    match = DIFF_STAT.search(result.stdout)
    if match is None:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2) or 0), int(match.group(3) or 0))


def _diff_evidence_issues(root: Path, evidence: str) -> list[str]:
    """证据里的 `git show --shortstat --oneline <sha>` 必须与 git 实际一致。

    没有写该命令的旧卡跳过；新卡由 check-spec 要求写（让数字可机械核对）。
    """
    issues: list[str] = []
    lines = evidence.splitlines()
    for index, line in enumerate(lines):
        match = DIFF_CMD.search(line)
        if match is None:
            continue
        sha = match.group(1)
        expected = _git_shortstat(root, sha)
        if expected is None:
            issues.append(f"证据引用的提交 {sha} 不可读（检查是否已提交）")
            continue
        actual: tuple[int, int, int] | None = None
        for follow in lines[index + 1 : index + 4]:
            stat = DIFF_STAT.search(follow)
            if stat is not None:
                actual = (
                    int(stat.group(1)),
                    int(stat.group(2) or 0),
                    int(stat.group(3) or 0),
                )
                break
        if actual is None:
            issues.append(f"证据缺少 {sha} 的 shortstat 输出")
        elif actual != expected:
            issues.append(f"证据的 diff 统计与 {sha} 实际不符：证据 {actual}，git {expected}")
    return issues


def _review_verify_issue(text: str) -> str | None:
    """门禁表的「收口全量（回填）」必须已有可复核结果；旧模板没有该行则跳过。"""
    match = REVIEW_VERIFY_ROW.search(text)
    if match is None:
        return None
    value = match.group(1).strip()
    if not value or "待收口" in value:
        return "「收口全量（回填）」尚未回填；先跑 make verify（自动回填）"
    if "pytest" not in value and "passed" not in value and "make verify" not in value:
        return "「收口全量（回填）」缺少 pytest/passed 结果"
    return None


def check(root: Path, feature: str) -> list[str]:
    """返回阻断收口的问题；空列表表示可以收口。"""
    problems: list[str] = []
    trace_issue = trace_gate(root)
    if trace_issue is not None:
        problems.append(trace_issue)

    card = find_card(root, feature)
    if card is None:
        return [f"{feature}：在 docs/tasks/*/F-{feature[2:]}.md 中找不到执行卡"]

    meta = parse_frontmatter(read(card))
    status = meta.get("status", "")
    if status != "review":
        label = STATUS_LABEL.get(status, status or "缺失")
        problems.append(f"{card}：frontmatter status 不是 review（当前 {label}）")

    text = read(card)
    evidence = section(text, "4. 证据")
    if "```" not in evidence:
        problems.append(f"{card}：第 4 节证据缺少命令输出代码块")
    problems.extend(f"{card}：{issue}" for issue in _diff_evidence_issues(root, evidence))

    review_path = root / "docs" / "reviews" / card.parent.name / f"{feature}.md"
    if not review_path.exists():
        problems.append(f"{review_path}：评审记录不存在")
    else:
        review_text = read(review_path)
        verdict = conclusion_verdict(review_text)
        if verdict == "不通过":
            problems.append(f"{review_path}：结论为不通过")
        elif verdict is None:
            problems.append(f"{review_path}：结论未写明通过")
        security_issue = _security_issue(review_text, meta)
        if security_issue is not None:
            problems.append(f"{review_path}：{security_issue}")
        verify_issue = _review_verify_issue(review_text)
        if verify_issue is not None:
            problems.append(f"{review_path}：{verify_issue}")

    current = current_sections(root / "docs" / "STATUS.md")
    pattern = re.compile(rf"\b{re.escape(feature)}\b")
    if pattern.search(current["已完成"]):
        problems.append("docs/STATUS.md：已在「已完成」，无需重复收口")
    if not (pattern.search(current["进行中"]) or pattern.search(current["下一步"])):
        problems.append("docs/STATUS.md：未出现在「进行中」或「下一步」")
    return problems


def _security_section(text: str) -> str:
    """匹配 `## 安全评审` 及其带后缀（如 `## 安全评审（T3）`）的标题。"""
    match = re.search(rf"^## {re.escape(SECURITY_HEADING)}[^\n]*$", text, re.M)
    if match is None:
        return ""
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def _security_issue(review_text: str, meta: dict[str, str]) -> str | None:
    """T3 必须有独立安全评审小节与“通过”结论；其他风险级别不强制。"""
    if meta.get("risk") != "T3":
        return None
    section_text = _security_section(review_text)
    if not section_text:
        return "T3 缺少 `## 安全评审` 小节"
    match = SECURITY_CONCLUSION.search(section_text)
    if match is None:
        return "T3 安全评审缺少 `结论：通过/有条件通过/不通过`"
    if match.group(1) != "通过":
        return f"T3 安全评审结论为「{match.group(1)}」，收口要求通过"
    return None


def set_status(card: Path, status: str) -> None:
    text = read(card)
    match = FRONTMATTER.match(text)
    if not match:
        raise SystemExit(f"{card}：缺少 frontmatter")
    block = match.group(1)
    block = re.sub(r"^status: .+$", f"status: {status}", block, count=1, flags=re.M)
    block = re.sub(
        r"^updated: .+$", f"updated: {date.today().isoformat()}", block, count=1, flags=re.M
    )
    card.write_text(f"---\n{block}\n---\n" + text[match.end() :], encoding="utf-8")


def tick_completion(completion: str) -> str:
    """只勾选可机械验证的项；提交类条目留给提交后确认。"""
    return "".join(
        line.replace("- [ ] ", "- [x] ", 1)
        if line.startswith("- [ ] ") and "提交" not in line
        else line
        for line in completion.splitlines(keepends=True)
    )


def apply(root: Path, feature: str) -> list[str]:
    problems = check(root, feature)
    if problems:
        return problems

    card = find_card(root, feature)
    if card is None:
        return [f"{feature}：找不到执行卡"]
    set_status(card, "done")

    text = read(card)
    completion = section(text, "6. 完成的定义")
    if completion:
        card.write_text(text.replace(completion, tick_completion(completion), 1), encoding="utf-8")

    subprocess.run(  # noqa: S603 - 固定仓库内脚本与解释器
        [sys.executable, str(root / "scripts" / "gen_tasks.py")],
        cwd=root,
        check=True,
    )
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="feature 收口检查/机械更新")
    parser.add_argument("feature", help="feature 编号，如 F-06")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="只检查，不写文件（默认）")
    parser.add_argument("--apply", action="store_true", help="更新 frontmatter 并生成 tasks.md")
    parser.add_argument("--evidence", default="", help="已废弃：证据写执行卡第 4 节")
    args = parser.parse_args()

    if not re.fullmatch(r"F-\d{2}", args.feature):
        print(f"feature 编号不合法：{args.feature}", file=sys.stderr)
        return 2

    root = args.root.resolve()
    if args.apply:
        if already_closed(root, args.feature):
            print(f"{args.feature}：已收口，无需修改。")
            return 0
        problems = apply(root, args.feature)
        if problems:
            print(f"{args.feature} 不能收口：", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        print(f"{args.feature}：frontmatter 已置 done，tasks.md 已重新生成。")
        print("剩余手工步骤：")
        print("  1. make gen-tasks && make dashboard；")
        print("  2. 更新 docs/STATUS.md：从「进行中」「下一步」移除该 feature，")
        print("     并在「已完成」追加一行；")
        print(f"  3. 提交 docs({args.feature}): 收口状态与证据；")
        print("  4. 提交后勾选执行卡完成定义中含“提交”的条目。")
        return 0

    if already_closed(root, args.feature):
        print(f"{args.feature}：已收口，无需检查。")
        return 0
    problems = check(root, args.feature)
    if problems:
        print(f"{args.feature} 尚未满足收口条件：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"{args.feature} 收口检查通过。")
    print("下一步：")
    print(f"  1. VERIFY_FEATURE={args.feature} make verify（全量并自动回填评审记录）")
    print(f"  2. python3 scripts/close_feature.py {args.feature} --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
