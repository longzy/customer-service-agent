#!/usr/bin/env python3
"""文档一致性与 Spec 结构检查。

用法：
    python3 scripts/check-docs.py

检查项见 docs/process/sdd.md 第 6 节。
退出码：0 全部通过；1 存在错误。
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECS_ROOT = os.path.join(ROOT, "docs", "specs")
TASKS_ROOT = os.path.join(ROOT, "docs", "tasks")

SKIP_DIRS = {".git", ".venv", "node_modules", ".next", ".uv-cache", ".pnpm-store", "coverage"}

STATUS_WORDS = {
    "未开始",
    "草案",
    "拟议",
    "等待评审",
    "已批准",
    "进行中",
    "阻塞",
    "已完成",
    "已暂停",
    "已关闭",
    "已清零",
    "待确认",
    "待开工许可",
}

CURRENT_REQUIRED_FIELDS = [
    "更新日期",
    "项目阶段",
    "当前状态",
    "当前 Milestone",
    "最近验证",
    "已完成",
    "进行中",
    "阻塞",
    "下一步",
    "待确认决策",
]

SPEC_REQUIRED_FILES = [
    "requirements.md",
    "design.md",
    "acceptance.md",
    "tasks.md",
    "clarifications.md",
]

GATE_OPEN_STATUSES = ("待开工许可", "已确认")
SPEC_DIR_PATTERN = re.compile(r"^\d{3}-[a-z0-9-]+$")
CARD_PATTERN = re.compile(r"^T-\d{2}\.md$")

errors = []
checked = {"links": 0, "files": 0, "acs": 0, "cards": 0, "specs": 0, "skipped": 0}


def rel(path):
    return os.path.relpath(path, ROOT)


def md_files():
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name.endswith(".md"):
                yield os.path.join(base, name)


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def doc_status(path):
    header = "\n".join(read(path).splitlines()[:15])
    match = re.search(r"^- 状态：(.+)$", header, re.M)
    return match.group(1).strip() if match else ""


def check_links(files):
    pattern = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")
    for path in files:
        for target in pattern.findall(read(path)):
            if target.startswith(("http", "mailto:")):
                continue
            checked["links"] += 1
            resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not os.path.exists(resolved):
                errors.append(f"{rel(path)}：链接目标不存在 {target}")


def check_status_words(files):
    """只检查文件头部的文档状态，避免与组件状态清单混淆。"""
    status = re.compile(r"^- 状态：(.+)$", re.M)
    for path in files:
        header = "\n".join(read(path).splitlines()[:15])
        for value in status.findall(header):
            token = re.split(r"[（(，,、\s]", value.strip())[0]
            if token and token not in STATUS_WORDS:
                errors.append(f"{rel(path)}：状态词不在允许集合内：{token}")


def check_current_fields():
    text = read(os.path.join(ROOT, "docs", "CURRENT.md"))
    for field in CURRENT_REQUIRED_FIELDS:
        if field not in text:
            errors.append(f"docs/CURRENT.md：缺少规范第 5 节要求的字段 {field}")


def spec_dirs():
    """返回 (里程碑, 规格目录名, 绝对路径)，并校验命名与编号唯一。"""
    found = []
    if not os.path.isdir(SPECS_ROOT):
        return found
    for milestone in sorted(os.listdir(SPECS_ROOT)):
        milestone_path = os.path.join(SPECS_ROOT, milestone)
        if not os.path.isdir(milestone_path):
            continue
        numbers = {}
        for name in sorted(os.listdir(milestone_path)):
            path = os.path.join(milestone_path, name)
            if not os.path.isdir(path):
                continue
            if not SPEC_DIR_PATTERN.match(name):
                errors.append(f"{rel(path)}：规格目录名不符合 NNN-slug 约定")
                continue
            number = name.split("-")[0]
            if number in numbers:
                errors.append(f"{milestone}：编号 {number} 重复（{numbers[number]} 与 {name}）")
            numbers[number] = name
            found.append((milestone, name, path))
    return found


def check_spec_structure(specs):
    for milestone, name, path in specs:
        checked["specs"] += 1
        for required in SPEC_REQUIRED_FILES:
            if not os.path.exists(os.path.join(path, required)):
                errors.append(f"docs/specs/{milestone}/{name}：缺少必需文件 {required}")


def check_ac_coverage(specs):
    for milestone, name, path in specs:
        acceptance = os.path.join(path, "acceptance.md")
        tasks = os.path.join(path, "tasks.md")
        if not (os.path.exists(acceptance) and os.path.exists(tasks)):
            continue
        acs = sorted(set(re.findall(r"\bAC-\d{2}\b", read(acceptance))))
        tasks_text = read(tasks)
        checked["acs"] += len(acs)
        for ac in acs:
            if ac not in tasks_text:
                errors.append(f"docs/specs/{milestone}/{name}/tasks.md：缺少对 {ac} 的引用")


def check_task_dirs(specs):
    spec_names = {name for _, name, _ in specs}
    if not os.path.isdir(TASKS_ROOT):
        return
    for name in sorted(os.listdir(TASKS_ROOT)):
        path = os.path.join(TASKS_ROOT, name)
        if not os.path.isdir(path):
            continue
        if not SPEC_DIR_PATTERN.match(name):
            errors.append(f"{rel(path)}：执行卡目录名不符合 NNN-slug 约定")
            continue
        if name not in spec_names:
            errors.append(f"{rel(path)}：没有同名规格目录 docs/specs/*/{name}")
        for card in sorted(os.listdir(path)):
            if not card.endswith(".md"):
                continue
            if not CARD_PATTERN.match(card):
                errors.append(f"{rel(os.path.join(path, card))}：执行卡命名应为 T-XX.md")


PATH_PREFIXES = ("docs/", "services/", "packages/", "tests/", "scripts/", "apps/", "migrations/")
PATH_TOKEN = re.compile(r"`([^`\n]+)`")


def check_card_paths():
    """执行卡里以反引号写出的仓库路径必须真实存在。"""
    if not os.path.isdir(TASKS_ROOT):
        return
    for base, _dirs, names in os.walk(TASKS_ROOT):
        for card in sorted(names):
            if not CARD_PATTERN.match(card):
                continue
            card_path = os.path.join(base, card)
            for token in PATH_TOKEN.findall(read(card_path)):
                if not token.startswith(PATH_PREFIXES):
                    continue
                if "<" in token or "*" in token or " " in token:
                    continue
                if os.path.exists(os.path.join(ROOT, token.rstrip("/"))):
                    continue
                errors.append(f"{rel(card_path)}：引用的路径不存在 {token}")


def resolve_reference(card_path, ref):
    """依次在仓库根、执行卡所在目录及其各级上级目录中解析相对引用。"""
    candidates = [os.path.join(ROOT, ref)]
    directory = os.path.dirname(card_path)
    while True:
        candidates.append(os.path.join(directory, ref))
        parent = os.path.dirname(directory)
        if directory == ROOT or parent == directory:
            break
        directory = parent
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.normpath(candidate)
    return None


def check_design_card_gate():
    if not os.path.isdir(TASKS_ROOT):
        return
    for base, _dirs, names in os.walk(TASKS_ROOT):
        for card in sorted(names):
            if not CARD_PATTERN.match(card):
                continue
            card_path = os.path.join(base, card)
            status = doc_status(card_path)
            if not status.startswith(GATE_OPEN_STATUSES):
                checked["skipped"] += 1
                print(f"跳过执行卡 {rel(card_path)}：状态为 {status or '未声明'}")
                continue
            checked["cards"] += 1
            for line in read(card_path).splitlines():
                if not line.startswith("- 依据："):
                    continue
                for ref in re.findall(r"`([^`]+\.md)`", line):
                    target = resolve_reference(card_path, ref)
                    if target is None:
                        errors.append(f"{rel(card_path)}：依据文档不存在 {ref}")
                        continue
                    if not doc_status(target).startswith(("已批准", "已清零")):
                        errors.append(
                            f"{rel(card_path)}：状态为 {status}，但依据文档 {rel(target)} 尚未批准"
                        )


def main():
    files = sorted(md_files())
    checked["files"] = len(files)
    specs = spec_dirs()

    check_links(files)
    check_status_words(files)
    check_current_fields()
    check_spec_structure(specs)
    check_ac_coverage(specs)
    check_task_dirs(specs)
    check_card_paths()
    check_design_card_gate()

    if errors:
        print(f"文档检查失败，{len(errors)} 个问题：")
        for item in errors:
            print("  - " + item)
        return 1

    print(
        f"文档检查通过：{checked['files']} 个文件、{checked['links']} 条链接、"
        f"{checked['specs']} 个规格目录、{checked['acs']} 条 AC、"
        f"{checked['cards']} 张执行卡已检查、{checked['skipped']} 张跳过。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
